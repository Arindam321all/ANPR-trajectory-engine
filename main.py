"""
Entry point for the ingestion side of the system: starts one CameraTracker
per camera defined in config.yaml, each in its own thread, so a slow or
disconnected camera never blocks the others. Also runs a background loop
that periodically rebuilds cross-camera trajectories from new detections.

For very high camera counts (dozens+), swap threading for multiprocessing
or separate worker containers/pods — the CameraTracker class itself has no
shared mutable state other than the DB, so it parallelizes cleanly either way.
"""
import logging
import threading
import time

from config_loader import all_camera_ids
from db.database import init_db
from tracking.camera_tracker import CameraTracker
from tracking.trajectory_engine import rebuild_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

TRAJECTORY_REBUILD_INTERVAL_SECONDS = 30


def trajectory_rebuild_loop(stop_event: threading.Event):
    while not stop_event.is_set():
        time.sleep(TRAJECTORY_REBUILD_INTERVAL_SECONDS)
        try:
            result = rebuild_all()
            logger.info("Trajectory rebuild: %s", result)
        except Exception:
            logger.exception("Trajectory rebuild failed")


def main():
    init_db()

    camera_ids = all_camera_ids()
    logger.info("Starting ingestion for %d cameras: %s", len(camera_ids), camera_ids)

    threads = []
    for cam_id in camera_ids:
        tracker = CameraTracker(cam_id)
        t = threading.Thread(target=tracker.run, name=f"tracker-{cam_id}", daemon=True)
        t.start()
        threads.append(t)

    stop_event = threading.Event()
    rebuild_thread = threading.Thread(
        target=trajectory_rebuild_loop, args=(stop_event,), name="trajectory-rebuild", daemon=True
    )
    rebuild_thread.start()

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        stop_event.set()


if __name__ == "__main__":
    main()
