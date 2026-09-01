"""
REST API for the ANPR engine. Run with:
    uvicorn api.main:app --host 0.0.0.0 --port 8000

Serves the dashboard at "/" and JSON analytics under "/analytics/*",
raw data under "/detections" and "/trajectory/*".
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from db import database
from tracking import trajectory_engine
from analytics import traffic_analytics
from config_loader import get_config, all_camera_ids

app = FastAPI(
    title="City-Wide ANPR Trajectory & Traffic Analytics API",
    description="PS127 — Multi-camera ANPR trajectory tracking and urban traffic analytics engine",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"


@app.on_event("startup")
def startup():
    database.init_db()


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
        legs = [dict(r) for r in existing]

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


@app.get("/analytics/overspeed")
def overspeed(limit: int = 100):
    return traffic_analytics.overspeed_report(limit)


@app.get("/analytics/loitering/{plate}")
def loitering(plate: str):
    return traffic_analytics.loitering_check(plate.upper())


@app.get("/analytics/summary")
def summary(window_minutes: int = 60):
    return traffic_analytics.city_summary(window_minutes)


@app.get("/watchlist/check/{plate}")
def check_watchlist(plate: str):
    row = database.is_watchlisted(plate.upper())
    return {"plate_number": plate.upper(), "watchlisted": row is not None,
            "reason": row["reason"] if row else None}


@app.post("/watchlist/add")
def add_watchlist(plate: str, reason: str = "unspecified"):
    database.add_to_watchlist(plate.upper(), reason)
    return {"status": "added", "plate_number": plate.upper()}
