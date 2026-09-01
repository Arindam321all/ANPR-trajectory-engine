"""
Turns raw detections + trajectory legs into city-wide traffic analytics:
congestion per camera, a density heatmap grid, overspeed alerts, and a
loitering/suspicious-dwell flag for the watchlist use case.
"""
import math
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from config_loader import get_config, all_camera_ids, get_camera
from db import database


def _since(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def congestion_report(window_minutes: int | None = None) -> list[dict]:
    """Vehicles/minute at each camera over the trailing window — the core
    'is this junction jammed right now' signal."""
    cfg = get_config()["analytics"]
    window = window_minutes or cfg["congestion_window_minutes"]
    since_iso = _since(window)

    report = []
    for cam_id in all_camera_ids():
        cam = get_camera(cam_id)
        rows = database.get_recent_detections(cam_id, since_iso)
        count = len(rows)
        rate_per_min = round(count / window, 2) if window else count

        # simple 3-tier congestion classification; tune thresholds per city
        if rate_per_min >= 15:
            level = "heavy"
        elif rate_per_min >= 6:
            level = "moderate"
        else:
            level = "light"

        report.append({
            "camera_id": cam_id,
            "camera_name": cam["name"],
            "lat": cam["lat"], "lon": cam["lon"],
            "vehicles_in_window": count,
            "vehicles_per_minute": rate_per_min,
            "congestion_level": level,
            "window_minutes": window,
        })
    return sorted(report, key=lambda r: r["vehicles_per_minute"], reverse=True)


def heatmap_grid(window_minutes: int = 60) -> list[dict]:
    """Aggregates detections into lat/lon grid cells for a map heat-layer.
    Grid size is configurable (defaults to ~200m cells)."""
    cfg = get_config()["analytics"]
    cell_size = cfg["heatmap_grid_size_deg"]
    since_iso = _since(window_minutes)

    rows = database.get_all_recent_for_heatmap(since_iso)
    cam_counts = {r["camera_id"]: r["cnt"] for r in rows}

    cells = defaultdict(int)
    cell_meta = {}
    for cam_id, count in cam_counts.items():
        cam = get_camera(cam_id)
        cell_lat = round(cam["lat"] / cell_size) * cell_size
        cell_lon = round(cam["lon"] / cell_size) * cell_size
        key = (cell_lat, cell_lon)
        cells[key] += count
        cell_meta[key] = cam["name"]

    return [
        {"lat": lat, "lon": lon, "intensity": cnt, "nearest_camera": cell_meta[(lat, lon)]}
        for (lat, lon), cnt in cells.items()
    ]


def overspeed_report(limit: int = 100) -> list[dict]:
    rows = database.get_overspeed_legs(limit)
    return [dict(r) for r in rows]


def loitering_check(plate_number: str) -> dict:
    """Flags a vehicle that has stayed near the same camera far longer than
    a normal pass-through (useful for parked/suspicious-vehicle alerts)."""
    cfg = get_config()["analytics"]
    threshold_min = cfg["loitering_minutes_threshold"]

    detections = database.get_detections_for_plate(plate_number)
    if len(detections) < 2:
        return {"plate_number": plate_number, "loitering": False}

    from dateutil import parser as dtparser
    by_camera = defaultdict(list)
    for d in detections:
        by_camera[d["camera_id"]].append(dtparser.isoparse(d["timestamp"]))

    for cam_id, times in by_camera.items():
        span_minutes = (max(times) - min(times)).total_seconds() / 60.0
        if span_minutes >= threshold_min:
            return {
                "plate_number": plate_number, "loitering": True,
                "camera_id": cam_id, "duration_minutes": round(span_minutes, 1),
            }
    return {"plate_number": plate_number, "loitering": False}


def city_summary(window_minutes: int = 60) -> dict:
    """Top-line dashboard numbers."""
    since_iso = _since(window_minutes)
    all_plates = database.get_distinct_plates_since(since_iso)
    congestion = congestion_report()
    overspeed = database.get_overspeed_legs(limit=1000)

    busiest = congestion[0] if congestion else None
    return {
        "window_minutes": window_minutes,
        "unique_vehicles_seen": len(all_plates),
        "total_cameras": len(all_camera_ids()),
        "busiest_camera": busiest["camera_name"] if busiest else None,
        "busiest_camera_rate_per_min": busiest["vehicles_per_minute"] if busiest else 0,
        "overspeed_incidents_total": len(overspeed),
        "congestion_by_camera": congestion,
    }
