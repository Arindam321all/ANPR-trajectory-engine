"""Insert fresh synthetic violation events for dashboard testing.

Run from this directory with:
    python demo_alert_seed.py
"""
from datetime import datetime, timedelta, timezone

from alerting import alert_engine
from config_loader import get_config
from db import database


def detection(plate, camera_id, when, vehicle_type, **context):
    event = {
        "plate_number": plate,
        "camera_id": camera_id,
        "timestamp": when.isoformat(),
        "confidence": 0.98,
        "ocr_confidence": 0.96,
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
    return alert_engine.evaluate_detection(event)


def main():
    database.init_db()
    config = get_config()
    cameras = {camera["id"]: camera for camera in config["cameras"]}
    now = datetime.now(timezone.utc).replace(microsecond=0)

    # Add a fresh watchlist entry and trigger a blacklist alert.
    database.add_to_watchlist("TEST-BLACKLIST", "Dashboard alert demonstration")
    results = []
    results += detection("TEST-BLACKLIST", "CAM_001", now - timedelta(seconds=35), "car")

    # Supply the optional signal/lane evidence that real perception adapters provide.
    results += detection(
        "TEST-REDLIGHT", "CAM_002", now - timedelta(seconds=30), "car",
        signal_state="red", crossed_stop_line=True,
    )
    results += detection(
        "TEST-LANE", "CAM_003", now - timedelta(seconds=25), "truck",
        lane_type="two_wheeler",
    )
    results += detection(
        "TEST-NM-LANE", "CAM_004", now - timedelta(seconds=20), "car",
        lane_type="non_motorised",
    )

    # Configure directed restrictions for this test process only. The alerts
    # remain persisted after the process exits and are visible to the API.
    cameras["CAM_005"]["allowed_directions"] = ["north"]
    results += detection(
        "TEST-WRONGWAY", "CAM_005", now - timedelta(seconds=15), "car",
        travel_direction="south",
    )
    cameras["CAM_001"]["allowed_next_cameras"] = ["CAM_002"]
    cameras["CAM_003"]["temporary_one_way_to"] = ["CAM_004"]

    leg = {
        "plate_number": "TEST-ROUTE",
        "from_camera_id": "CAM_001",
        "to_camera_id": "CAM_003",
        "from_timestamp": (now - timedelta(seconds=50)).isoformat(),
        "to_timestamp": (now - timedelta(seconds=10)).isoformat(),
        "distance_km": 5.0,
        "duration_seconds": 40.0,
        "speed_kmph": 450.0,
        "is_overspeed": True,
    }
    database.insert_trajectory_leg(**leg)
    results += alert_engine.evaluate_leg(leg)

    one_way_leg = {
        "plate_number": "TEST-ONEWAY",
        "from_camera_id": "CAM_003",
        "to_camera_id": "CAM_005",
        "from_timestamp": (now - timedelta(seconds=45)).isoformat(),
        "to_timestamp": (now - timedelta(seconds=5)).isoformat(),
        "distance_km": 1.0,
        "duration_seconds": 40.0,
        "speed_kmph": 90.0,
        "is_overspeed": False,
    }
    database.insert_trajectory_leg(**one_way_leg)
    results += alert_engine.evaluate_leg(one_way_leg)

    print(f"Inserted {len(results)} dashboard test alerts.")
    print("Open http://localhost:8000 and wait up to 5 seconds for the alert rail.")
    print("Test plates: TEST-BLACKLIST, TEST-REDLIGHT, TEST-LANE, TEST-NM-LANE, TEST-WRONGWAY, TEST-ROUTE, TEST-ONEWAY")


if __name__ == "__main__":
    main()
