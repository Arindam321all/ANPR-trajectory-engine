"""
demo_seed.py — populate the ANPR database with realistic simulated traffic
so you can see the whole pipeline (congestion, trajectories, overspeed,
loitering) working immediately, without needing real camera footage or a
YOLO/OCR model download yet.

Run from inside the anpr_engine/anpr_engine folder (same place as main.py):

    python demo_seed.py

Then refresh the dashboard (or open http://localhost:8000 if it isn't
already running the API) — you'll see live-looking numbers, an overspeed
alert, and you can look up any of the printed plate numbers in the
trajectory search box.

This does NOT touch detection/OCR/YOLO at all — it writes straight to the
same SQLite database and calls the same trajectory_engine + analytics
modules your real camera pipeline uses, so everything downstream (API,
dashboard) behaves exactly as it will with real footage.
"""
import random
from datetime import datetime, timedelta, timezone

from db.database import init_db, insert_detection
from tracking.trajectory_engine import rebuild_all
from config_loader import all_camera_ids, get_camera

random.seed(42)

VEHICLE_TYPES = ["car", "car", "car", "bike", "truck", "bus"]

# Plates used for the three scripted demo scenarios below (normal trip,
# overspeed, loitering) -- kept OUT of the background noise pool so their
# story stays clean and doesn't pick up random unrelated sightings.
STORY_PLATES = {"KA05MH1234", "KA01AB9999", "KA41FZ2210"}

# A handful of plausible Indian-format plates (2 letters, 2 digits, 1-2 letters, 4 digits)
# used only for generic background traffic noise.
DEMO_PLATES = [
    "KA03BZ4521", "KA51HN0087", "KA02CG7743", "KA07LP5566", "KA19XR8830",
]


def simulate_city(minutes_of_history: int = 60, vehicles_per_camera_per_min: float = 4.0):
    cameras = all_camera_ids()
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=minutes_of_history)

    print(f"Simulating {minutes_of_history} minutes of traffic across {len(cameras)} cameras...")

    # 1. Background traffic: random one-off sightings at random cameras,
    #    spread across the whole window, to drive congestion numbers.
    total_random = 0
    t = start
    while t < now:
        for cam_id in cameras:
            if random.random() < 0.7:  # not every camera every tick
                plate = random.choice(DEMO_PLATES) if random.random() < 0.3 else _random_plate()
                insert_detection(
                    plate_number=plate, camera_id=cam_id,
                    timestamp=(t + timedelta(seconds=random.randint(0, 59))).isoformat(),
                    confidence=round(random.uniform(0.75, 0.98), 2),
                    ocr_confidence=round(random.uniform(0.6, 0.95), 2),
                    vehicle_type=random.choice(VEHICLE_TYPES),
                )
                total_random += 1
        t += timedelta(minutes=1 / vehicles_per_camera_per_min)
    print(f"  inserted {total_random} background detections")

    # 2. A clean cross-camera journey: KA05MH1234 drives CAM_001 -> CAM_002 -> CAM_004
    #    at a normal, legal speed (this will show a nice trajectory with no flags).
    cam_chain = cameras[:3] if len(cameras) >= 3 else cameras
    t0 = now - timedelta(minutes=10)
    for i, cam_id in enumerate(cam_chain):
        insert_detection(
            plate_number="KA05MH1234", camera_id=cam_id,
            timestamp=(t0 + timedelta(minutes=3 * i)).isoformat(),
            confidence=0.94, ocr_confidence=0.9, vehicle_type="car",
        )
    print("  inserted a normal-speed trajectory for KA05MH1234")

    # 3. An overspeeding vehicle: KA01AB9999 covers two connected cameras
    #    far too quickly for the posted limit.
    if len(cameras) >= 2:
        cam_a, cam_b = cameras[0], cameras[1]
        t1 = now - timedelta(minutes=5)
        insert_detection("KA01AB9999", cam_a, t1.isoformat(), 0.9, 0.88, vehicle_type="bike")
        insert_detection("KA01AB9999", cam_b, (t1 + timedelta(seconds=25)).isoformat(),
                          0.91, 0.87, vehicle_type="bike")
        print("  inserted an overspeed trajectory for KA01AB9999")

    # 4. A loitering vehicle: KA41FZ2210 lingers at one camera for 20+ minutes
    #    (e.g. parked / suspicious dwell).
    if cameras:
        cam_id = cameras[-1]
        t2 = now - timedelta(minutes=25)
        for offset in (0, 10, 22):
            insert_detection("KA41FZ2210", cam_id, (t2 + timedelta(minutes=offset)).isoformat(),
                              0.88, 0.85, vehicle_type="car")
        print(f"  inserted a loitering pattern for KA41FZ2210 at {cam_id}")

    print("\nRebuilding cross-camera trajectories...")
    result = rebuild_all(since_iso=start.isoformat())
    print(f"  {result}")

    print("\nDone. Try these in the dashboard's Plate Trajectory Lookup box:")
    print("  KA05MH1234   -> normal 3-camera trip")
    print("  KA01AB9999   -> flagged OVERSPEED leg")
    print("  KA41FZ2210   -> flagged LOITERING at one camera")


def _random_plate() -> str:
    letters1 = "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ", k=2))
    digits1 = f"{random.randint(1, 60):02d}"
    letters2 = "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ", k=random.choice([1, 2])))
    digits2 = f"{random.randint(0, 9999):04d}"
    return f"{letters1}{digits1}{letters2}{digits2}"


if __name__ == "__main__":
    init_db()
    simulate_city()