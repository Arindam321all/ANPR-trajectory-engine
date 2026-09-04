"""
The core "multi-camera trajectory tracking" logic.

A vehicle's plate is the re-identification key across cameras (no visual
re-ID needed since OCR already gives us a near-unique ID). For a given
plate:

  1. Pull every detection row, already sorted by timestamp.
  2. Walk consecutive pairs of sightings (cam_i -> cam_i+1).
  3. If the two cameras are direct road-neighbors (config.yaml), compute
     elapsed time and use the configured road distance to get speed.
  4. If they are NOT direct neighbors (vehicle passed unmonitored roads,
     or camera outage), we still record the leg but mark distance as
     "unknown" (straight-line haversine fallback) so analytics can flag it
     as a lower-confidence leg instead of dropping it silently.
  5. Persist each leg to `trajectory_legs` for fast API/analytics queries.

Run this periodically (e.g. every 30s via a scheduler / cron / APScheduler)
or after each new detection batch — it's idempotent-safe to rerun since it
only needs the latest detection pair per plate to add new legs; for a full
rebuild use `rebuild_all()`.
"""
import math
from datetime import datetime
from dateutil import parser as dtparser

from config_loader import get_config, get_camera
from db import database
from tracking import routing
from alerting import alert_engine


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _distance_between(cam_a: str, cam_b: str) -> tuple[float, bool, list]:
    """Returns (distance_km, is_confirmed_road_distance, route_coords).
    Uses OSMnx routing to find the shortest optimistic path between cameras.
    Falls back to straight-line haversine distance if no path found."""
    cam_a_cfg, cam_b_cfg = get_camera(cam_a), get_camera(cam_b)
    
    coords, dist = routing.get_optimistic_route(
        cam_a_cfg["lat"], cam_a_cfg["lon"], 
        cam_b_cfg["lat"], cam_b_cfg["lon"]
    )
    
    if coords is not None and dist > 0:
        return dist, True, coords
        
    # Fallback
    dist = _haversine_km(cam_a_cfg["lat"], cam_a_cfg["lon"], cam_b_cfg["lat"], cam_b_cfg["lon"])
    return dist, False, []


def build_trajectory_for_plate(plate_number: str) -> list[dict]:
    """Computes (and persists) every leg of a single plate's city-wide route.
    Returns the list of legs as plain dicts for direct API use."""
    detections = database.get_detections_for_plate(plate_number)
    if len(detections) < 2:
        return []

    cfg = get_config()["analytics"]
    legs = []

    for i in range(len(detections) - 1):
        a, b = detections[i], detections[i + 1]
        if a["camera_id"] == b["camera_id"]:
            continue  # same camera re-sighting, not a hop

        t_a, t_b = dtparser.isoparse(a["timestamp"]), dtparser.isoparse(b["timestamp"])
        duration_s = (t_b - t_a).total_seconds()
        if duration_s <= 0:
            continue

        distance_km, confirmed, route_coords = _distance_between(a["camera_id"], b["camera_id"])
        speed_kmph = distance_km / (duration_s / 3600.0)

        to_cam_cfg = get_camera(b["camera_id"])
        limit = to_cam_cfg["speed_limit_kmph"] + cfg["overspeed_tolerance_kmph"]
        is_overspeed = confirmed and speed_kmph > limit

        database.insert_trajectory_leg(
            plate_number=plate_number,
            from_camera_id=a["camera_id"], to_camera_id=b["camera_id"],
            from_timestamp=a["timestamp"], to_timestamp=b["timestamp"],
            distance_km=distance_km, duration_seconds=duration_s,
            speed_kmph=speed_kmph, is_overspeed=is_overspeed,
        )
        leg = {
            "plate_number": plate_number,
            "from_camera": a["camera_id"], "to_camera": b["camera_id"],
            "from_camera_id": a["camera_id"], "to_camera_id": b["camera_id"],
            "from_timestamp": a["timestamp"], "to_timestamp": b["timestamp"],
            "distance_km": round(distance_km, 3),
            "duration_seconds": round(duration_s, 1),
            "speed_kmph": round(speed_kmph, 1),
            "road_distance_confirmed": confirmed,
            "is_overspeed": is_overspeed,
            "route_coords": route_coords,
        }
        alert_engine.evaluate_leg(leg)
        legs.append(leg)

    return legs


def rebuild_all(since_iso: str | None = None):
    """Rebuild trajectory legs for every plate seen since `since_iso`
    (or all-time if omitted). Useful as a periodic batch job."""
    since_iso = since_iso or "1970-01-01T00:00:00"
    plates = database.get_distinct_plates_since(since_iso)
    total_legs = 0
    for plate in plates:
        legs = build_trajectory_for_plate(plate)
        total_legs += len(legs)
    return {"plates_processed": len(plates), "legs_created": total_legs}
