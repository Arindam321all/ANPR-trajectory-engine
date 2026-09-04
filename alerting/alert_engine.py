"""Create deduplicated alerts from detections and trajectory legs."""
import hashlib
import json
import logging
from datetime import datetime, timezone

from config_loader import get_camera, get_config
from db import database
from alerting.notifiers import notify

logger = logging.getLogger(__name__)

_HEAVY_TYPES = {"truck", "bus", "heavy_vehicle"}


def _fingerprint(alert_type: str, identity: str) -> str:
    return hashlib.sha256(f"{alert_type}:{identity}".encode("utf-8")).hexdigest()


def _create(alert_type: str, severity: str, message: str, occurred_at: str,
            details: dict, plate_number: str | None = None,
            camera_id: str | None = None, from_camera_id: str | None = None,
            to_camera_id: str | None = None, identity: str | None = None) -> dict:
    fingerprint = _fingerprint(alert_type, identity or f"{plate_number}:{occurred_at}")
    alert_id, created = database.insert_alert(
        fingerprint, alert_type, severity, plate_number, camera_id,
        from_camera_id, to_camera_id, occurred_at, message, details,
    )
    if not created:
        return {"id": alert_id, "created": False, "alert_type": alert_type}

    alert = {
        "id": alert_id, "alert_type": alert_type, "severity": severity,
        "plate_number": plate_number, "camera_id": camera_id,
        "from_camera_id": from_camera_id, "to_camera_id": to_camera_id,
        "occurred_at": occurred_at, "message": message, "details": details,
    }
    if notify(alert):
        database.mark_alert_notified(alert_id)
    return {**alert, "created": True}


def evaluate_detection(detection: dict) -> list[dict]:
    """Evaluate a newly persisted sighting and its camera's restrictions.

    `signal_state`, `crossed_stop_line`, and `travel_direction` are optional
    observations supplied by a signal/lane vision module or an upstream camera
    adapter. Missing observations produce no related alert.
    """
    cfg = get_config().get("alerting", {}).get("rules", {})
    camera = get_camera(detection["camera_id"])
    plate = detection["plate_number"]
    timestamp = detection["timestamp"]
    alerts = []

    if cfg.get("blacklisted_vehicle", True):
        watchlist_row = database.is_watchlisted(plate)
        if watchlist_row:
            alerts.append(_create(
                "blacklisted_vehicle", "critical",
                f"Blacklisted vehicle {plate} detected at {camera['name']}", timestamp,
                {"reason": watchlist_row["reason"], "camera_name": camera["name"]},
                plate_number=plate, camera_id=camera["id"],
                identity=f"{plate}:{camera['id']}:{timestamp}",
            ))

    vehicle_type = (detection.get("vehicle_type") or "").lower()
    lane_type = (detection.get("lane_type") or camera.get("lane_type") or "").lower()
    restricted = set(camera.get("restricted_vehicle_types", []))
    if lane_type == "two_wheeler" and (vehicle_type in _HEAVY_TYPES or vehicle_type == "car"):
        restricted.add(vehicle_type)
    if lane_type == "non_motorised" and vehicle_type:
        restricted.add(vehicle_type)
    if cfg.get("restricted_lane", True) and restricted:
        alerts.append(_create(
            "restricted_lane", "high",
            f"{vehicle_type or 'Vehicle'} {plate} entered {lane_type or 'restricted'} lane",
            timestamp, {"vehicle_type": vehicle_type, "lane_type": lane_type,
                        "camera_name": camera["name"]},
            plate_number=plate, camera_id=camera["id"],
            identity=f"{plate}:{camera['id']}:{timestamp}",
        ))

    if (cfg.get("signal_jump", True)
            and str(detection.get("signal_state", "")).lower() == "red"
            and detection.get("crossed_stop_line") is True):
        alerts.append(_create(
            "signal_jump", "high", f"Vehicle {plate} crossed a red signal at {camera['name']}",
            timestamp, {"signal_state": "red", "crossed_stop_line": True},
            plate_number=plate, camera_id=camera["id"],
            identity=f"{plate}:{camera['id']}:{timestamp}",
        ))

    allowed_directions = camera.get("allowed_directions", [])
    direction = detection.get("travel_direction")
    if cfg.get("wrong_way", True) and direction and allowed_directions and direction not in allowed_directions:
        alerts.append(_create(
            "wrong_way", "high", f"Vehicle {plate} travelled in the wrong direction at {camera['name']}",
            timestamp, {"travel_direction": direction, "allowed_directions": allowed_directions},
            plate_number=plate, camera_id=camera["id"],
            identity=f"{plate}:{camera['id']}:{timestamp}",
        ))
    return alerts


def evaluate_leg(leg: dict) -> list[dict]:
    """Evaluate speed and directed-network restrictions for one trajectory leg."""
    cfg = get_config().get("alerting", {}).get("rules", {})
    from_camera = get_camera(leg["from_camera_id"])
    plate = leg["plate_number"]
    occurred_at = leg["to_timestamp"]
    alerts = []

    if cfg.get("overspeed", True) and leg.get("is_overspeed"):
        alerts.append(_create(
            "overspeed", "high",
            f"Vehicle {plate} travelled at {float(leg['speed_kmph']):.1f} km/h",
            occurred_at, {"speed_kmph": leg["speed_kmph"], "from_camera": leg["from_camera_id"],
                          "to_camera": leg["to_camera_id"]}, plate_number=plate,
            from_camera_id=leg["from_camera_id"], to_camera_id=leg["to_camera_id"],
            identity=f"{plate}:{leg['from_timestamp']}:{leg['to_timestamp']}:overspeed",
        ))

    allowed_next = from_camera.get("allowed_next_cameras")
    if cfg.get("route_deviation", True) and allowed_next and leg["to_camera_id"] not in allowed_next:
        alerts.append(_create(
            "route_deviation", "medium",
            f"Vehicle {plate} deviated from the configured route",
            occurred_at, {"allowed_next_cameras": allowed_next}, plate_number=plate,
            from_camera_id=leg["from_camera_id"], to_camera_id=leg["to_camera_id"],
            identity=f"{plate}:{leg['from_timestamp']}:{leg['to_timestamp']}:route",
        ))

    one_way = from_camera.get("temporary_one_way_to")
    if cfg.get("wrong_way", True) and one_way and leg["to_camera_id"] not in one_way:
        alerts.append(_create(
            "temporary_one_way_violation", "high",
            f"Vehicle {plate} used the wrong direction of a temporary one-way lane",
            occurred_at, {"allowed_destinations": one_way}, plate_number=plate,
            from_camera_id=leg["from_camera_id"], to_camera_id=leg["to_camera_id"],
            identity=f"{plate}:{leg['from_timestamp']}:{leg['to_timestamp']}:one-way",
        ))
    return alerts


def recent_alerts(window_minutes: int = 60, alert_type: str | None = None,
                  limit: int = 100) -> list[dict]:
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()
    result = []
    for row in database.get_recent_alerts(since, alert_type, limit):
        item = dict(row)
        item["details"] = json.loads(item.pop("details_json"))
        item["notified"] = bool(item["notified"])
        result.append(item)
    return result
