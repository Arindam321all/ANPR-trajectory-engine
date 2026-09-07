"""
REST API for the ANPR engine. Run with:
    uvicorn api.main:app --host 0.0.0.0 --port 8000

Serves the dashboard at "/" and JSON analytics under "/analytics/*",
raw data under "/detections" and "/trajectory/*".
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
from pathlib import Path
import threading
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from db import database
from tracking import trajectory_engine, routing
from analytics import traffic_analytics
from config_loader import get_config, all_camera_ids, get_camera
from alerting import alert_engine
from tracking.camera_tracker import CameraTracker

app = FastAPI(
    title="City-Wide ANPR Trajectory & Traffic Analytics API",
    description="PS127 — Multi-camera ANPR trajectory tracking and urban traffic analytics engine",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"
MAP_DIR = Path(__file__).parent.parent / "map"
UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
upload_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uploaded-video")
upload_jobs = {}
upload_jobs_lock = threading.Lock()
logger = logging.getLogger(__name__)

app.mount("/map", StaticFiles(directory=MAP_DIR), name="map")


@app.on_event("startup")
def startup():
    database.init_db()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _update_upload_job(job_id: str, **updates):
    with upload_jobs_lock:
        if job_id in upload_jobs:
            upload_jobs[job_id].update(updates)


def _process_uploaded_video(job_id: str, video_path: Path, camera_id: str):
    try:
        _update_upload_job(job_id, status="processing", started_at=datetime.now(timezone.utc).isoformat())
        tracker = CameraTracker(camera_id)

        def progress(frames_read, detections_logged, last_frame_at):
            _update_upload_job(job_id, frames_read=frames_read,
                               detections_logged=detections_logged,
                               last_frame_at=last_frame_at)

        if not tracker.run(source_override=str(video_path), on_progress=progress, replay=False):
            raise RuntimeError("Video source could not be opened")
        _update_upload_job(job_id, status="completed", completed_at=datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        logger.exception("Uploaded video job %s failed", job_id)
        _update_upload_job(job_id, status="failed", error=str(exc),
                           completed_at=datetime.now(timezone.utc).isoformat())
    finally:
        video_path.unlink(missing_ok=True)


@app.post("/uploads/videos", status_code=202)
async def upload_video(file: UploadFile = File(...), camera_id: str = Form(...)):
    """Queue one uploaded video for processing through the ANPR pipeline."""
    try:
        get_camera(camera_id)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown camera_id: {camera_id}")

    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported video format")

    job_id = uuid4().hex
    video_path = UPLOAD_DIR / f"{job_id}{extension}"
    size = 0
    try:
        with video_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Video exceeds the 500 MB limit")
                destination.write(chunk)
    except Exception:
        video_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    job = {
        "job_id": job_id, "filename": file.filename, "camera_id": camera_id,
        "status": "queued", "frames_read": 0, "detections_logged": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with upload_jobs_lock:
        upload_jobs[job_id] = job
    upload_executor.submit(_process_uploaded_video, job_id, video_path, camera_id)
    return job


@app.get("/uploads/videos/{job_id}")
def upload_video_status(job_id: str):
    with upload_jobs_lock:
        job = upload_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Upload job not found")
    return job


@app.get("/")
def dashboard():
    return FileResponse(DASHBOARD_DIR / "index.html")


@app.get("/cameras")
def list_cameras():
    cfg = get_config()
    return cfg["cameras"]


@app.get("/ingestion/status")
def ingestion_status():
    configured = {camera["id"]: camera for camera in get_config()["cameras"]}
    statuses = {row["camera_id"]: dict(row) for row in database.get_camera_statuses()}
    result = []
    for camera_id, camera in configured.items():
        status = statuses.get(camera_id, {
            "camera_id": camera_id, "state": "offline", "source": camera["source"],
            "frames_read": 0, "detections_logged": 0, "error": "Worker has not started",
        })
        status["camera_name"] = camera["name"]
        result.append(status)
    return result


@app.get("/detections")
def get_detections(plate: str = Query(..., description="Plate number, e.g. KA05MH1234")):
    rows = database.get_detections_for_plate(plate.upper())
    if not rows:
        raise HTTPException(status_code=404, detail=f"No detections found for plate {plate}")
    return [dict(r) for r in rows]


@app.get("/trajectory/{plate}")
def get_trajectory(plate: str, rebuild: bool = False):
    """Full cross-camera trajectory for a plate. Set rebuild=true to force
    recomputation of legs from raw detections (otherwise reads cached legs
    if present, else builds them on first request)."""
    plate = plate.upper()
    existing = database.get_trajectory_legs_for_plate(plate)
    if rebuild or not existing:
        legs = trajectory_engine.build_trajectory_for_plate(plate)
    else:
        legs = []
        for r in existing:
            leg = dict(r)
            # Map DB columns to API response structure
            leg["from_camera"] = leg["from_camera_id"]
            leg["to_camera"] = leg["to_camera_id"]
            
            # Attach route_coords dynamically if loaded from DB
            cam_a, cam_b = get_camera(leg["from_camera_id"]), get_camera(leg["to_camera_id"])
            coords, _ = routing.get_optimistic_route(
                cam_a["lat"], cam_a["lon"], cam_b["lat"], cam_b["lon"]
            )
            leg["route_coords"] = coords or []
            legs.append(leg)

    if not legs:
        detections = database.get_detections_for_plate(plate)
        if not detections:
            raise HTTPException(status_code=404, detail=f"No data found for plate {plate}")
        return {
            "plate_number": plate,
            "message": "Only one sighting so far — no cross-camera trajectory yet.",
            "detections": [dict(d) for d in detections],
        }

    loitering = traffic_analytics.loitering_check(plate)
    return {"plate_number": plate, "legs": legs, "loitering": loitering}


@app.post("/trajectory/rebuild-all")
def rebuild_all_trajectories(since_minutes: int = 1440):
    from datetime import datetime, timedelta, timezone
    since_iso = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).isoformat()
    return trajectory_engine.rebuild_all(since_iso)


@app.get("/analytics/congestion")
def congestion(window_minutes: int | None = None):
    return traffic_analytics.congestion_report(window_minutes)


@app.get("/analytics/heatmap")
def heatmap(window_minutes: int = 60):
    return traffic_analytics.heatmap_grid(window_minutes)


@app.get("/analytics/route-congestion")
def route_congestion(window_minutes: int = 60):
    report = traffic_analytics.route_congestion_report(window_minutes)
    for route in report:
        cam_a, cam_b = get_camera(route["from_camera_id"]), get_camera(route["to_camera_id"])
        coords, _ = routing.get_optimistic_route(cam_a["lat"], cam_a["lon"], cam_b["lat"], cam_b["lon"])
        route["route_coords"] = coords or []
    return report


@app.get("/analytics/overspeed")
def overspeed(limit: int = 100):
    return traffic_analytics.overspeed_report(limit)


@app.get("/analytics/loitering/{plate}")
def loitering(plate: str):
    return traffic_analytics.loitering_check(plate.upper())


@app.get("/analytics/summary")
def summary(window_minutes: int = 60):
    return traffic_analytics.city_summary(window_minutes)


@app.get("/alerts")
def alerts(window_minutes: int = 60, alert_type: str | None = None,
           limit: int = Query(100, ge=1, le=1000)):
    """Recent rule violations, including delivery status and evidence."""
    return alert_engine.recent_alerts(window_minutes, alert_type, limit)


@app.get("/watchlist/check/{plate}")
def check_watchlist(plate: str):
    row = database.is_watchlisted(plate.upper())
    return {"plate_number": plate.upper(), "watchlisted": row is not None,
            "reason": row["reason"] if row else None}


@app.post("/watchlist/add")
def add_watchlist(plate: str, reason: str = "unspecified"):
    database.add_to_watchlist(plate.upper(), reason)
    return {"status": "added", "plate_number": plate.upper()}
