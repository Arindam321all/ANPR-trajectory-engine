"""Add realistic recent traffic for dashboard/demo ranking checks.

Run from this directory:
    python demo_realistic_seed.py
"""
from datetime import datetime, timedelta, timezone

from alerting import alert_engine
from config_loader import get_config
from db import database
from tracking.trajectory_engine import build_trajectory_for_plate


def add_detection(plate, camera_id, when, vehicle_type, **context):
    event = {
        "plate_number": plate,
        "camera_id": camera_id,
        "timestamp": when.isoformat(),
        "confidence": 0.94,
        "ocr_confidence": 0.92,
        "vehicle_type": vehicle_type,
        **context,
    }
    database.insert_detection(
        plate_number=plate,
        camera_id=camera_id,
        timestamp=event["timestamp"],
        confidence=event["confidence"],
        ocr_confidence=event["ocr_confidence"],
        vehicle_type=vehicle_type,
        signal_state=event.get("signal_state"),
        crossed_stop_line=event.get("crossed_stop_line"),
        travel_direction=event.get("travel_direction"),
        lane_type=event.get("lane_type"),
    )
    alert_engine.evaluate_detection(event)


def add_trip(plate, vehicle_type, cameras, start, minutes_between):
    for index, camera_id in enumerate(cameras):
        add_detection(
            plate, camera_id, start + timedelta(minutes=index * minutes_between), vehicle_type
        )
    return build_trajectory_for_plate(plate)


def main():
    database.init_db()
    config = get_config()
    cameras = {camera["id"]: camera for camera in config["cameras"]}
    now = datetime.now(timezone.utc).replace(microsecond=0)

    # Recent normal traffic, with realistic inter-camera travel times.
    normal_trips = [
        ("DL01CR4821", "car", ["CAM_001", "CAM_002", "CAM_004"], 5),
        ("DL03MN7194", "car", ["CAM_002", "CAM_004", "CAM_005"], 6),
        ("HR26DK6318", "motorbike", ["CAM_004", "CAM_003", "CAM_001"], 4),
        ("UP16BT2086", "car", ["CAM_006", "CAM_001", "CAM_007"], 7),
        ("RJ14QA9052", "bus", ["CAM_005", "CAM_007"], 8),
    ]
    for index, (plate, vehicle_type, route, spacing) in enumerate(normal_trips):
        add_trip(plate, vehicle_type, route, now - timedelta(minutes=14 + index), spacing)

    # Moderate, plausible overspeed: route speeds generally land around 60-75 km/h.
    overspeed_trips = [
        ("DL04AE2716", "car", ["CAM_001", "CAM_002"], 3),
        ("KA05JM8430", "motorbike", ["CAM_002", "CAM_004"], 4),
        ("MH12RK5187", "car", ["CAM_003", "CAM_005"], 5),
    ]
    for index, (plate, vehicle_type, route, spacing) in enumerate(overspeed_trips):
        add_trip(plate, vehicle_type, route, now - timedelta(minutes=3 + index), spacing)

    # Current evidence-backed rule alerts.
    database.add_to_watchlist("DL08WQ3142", "Active vehicle watchlist demonstration")
    add_detection("DL08WQ3142", "CAM_004", now - timedelta(seconds=35), "car")
    add_detection(
        "DL02SIGNAL7", "CAM_005", now - timedelta(seconds=28), "car",
        signal_state="red", crossed_stop_line=True,
    )
    add_detection(
        "DL01LANE28", "CAM_006", now - timedelta(seconds=21), "truck",
        lane_type="two_wheeler",
    )

    # Directed-route and temporary one-way examples for the latest alert window.
    cameras["CAM_002"]["allowed_next_cameras"] = ["CAM_004"]
    cameras["CAM_003"]["temporary_one_way_to"] = ["CAM_004"]
    deviation_leg = {
        "plate_number": "DL09ROUTE63",
        "from_camera_id": "CAM_002",
        "to_camera_id": "CAM_007",
        "from_timestamp": (now - timedelta(seconds=70)).isoformat(),
        "to_timestamp": (now - timedelta(seconds=30)).isoformat(),
        "distance_km": 1.1,
        "duration_seconds": 40.0,
        "speed_kmph": 52.0,
        "is_overspeed": False,
    }
    database.insert_trajectory_leg(**deviation_leg)
    alert_engine.evaluate_leg(deviation_leg)

    one_way_leg = {
        "plate_number": "DL07ONEWAY",
        "from_camera_id": "CAM_003",
        "to_camera_id": "CAM_006",
        "from_timestamp": (now - timedelta(seconds=62)).isoformat(),
        "to_timestamp": (now - timedelta(seconds=24)).isoformat(),
        "distance_km": 0.9,
        "duration_seconds": 38.0,
        "speed_kmph": 42.0,
        "is_overspeed": False,
    }
    database.insert_trajectory_leg(**one_way_leg)
    alert_engine.evaluate_leg(one_way_leg)

    print("Inserted realistic recent traffic and alerts.")
    print("Normal plates: DL01CR4821, DL03MN7194, HR26DK6318, UP16BT2086, RJ14QA9052")
    print("Alert plates: DL08WQ3142, DL02SIGNAL7, DL01LANE28, DL09ROUTE63, DL07ONEWAY")
    print("Refresh the dashboard to see the newest records at the top.")


if __name__ == "__main__":
    main()
