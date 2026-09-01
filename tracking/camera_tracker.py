"""
Runs the full pipeline for ONE camera: read frames from its video/RTSP
source, detect plates, OCR them, and write clean detection events to the
database. Designed to run in its own thread/process (see main.py) so N
cameras run concurrently without blocking each other.

Dedup logic: the same physical vehicle is visible for many consecutive
frames while it crosses the camera's field of view. Without dedup you'd
get dozens of DB rows per real sighting. We use a short-memory cache
(plate -> last-seen time) and only log a new detection if the same plate
hasn't been seen at this camera in the last `DEDUP_WINDOW_SECONDS`.
"""
import time
import logging
from datetime import datetime, timezone

import cv2

from config_loader import get_camera, get_config
from detection.plate_detector import PlateDetector, VehicleDetector
from detection.ocr_reader import OCRReader, validate_plate
from db import database

logger = logging.getLogger(__name__)

DEDUP_WINDOW_SECONDS = 8.0


class CameraTracker:
    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.camera_cfg = get_camera(camera_id)
        self.frame_skip = get_config()["detection"]["frame_skip"]

        self.plate_detector = PlateDetector()
        self.vehicle_detector = VehicleDetector()
        self.ocr_reader = OCRReader()

        self._recent_plates: dict[str, float] = {}  # plate -> last-seen unix time

    def _already_seen_recently(self, plate: str, now: float) -> bool:
        last_seen = self._recent_plates.get(plate)
        if last_seen is not None and (now - last_seen) < DEDUP_WINDOW_SECONDS:
            return True
        self._recent_plates[plate] = now
        return False

    def _match_vehicle_type(self, plate_bbox: tuple, vehicles: list[dict]) -> str | None:
        """Assign a vehicle type to a plate by finding the vehicle box that
        contains the plate's bounding box (plate sits inside the vehicle)."""
        px1, py1, px2, py2 = plate_bbox
        for v in vehicles:
            vx1, vy1, vx2, vy2 = v["bbox"]
            if vx1 <= px1 and vy1 <= py1 and vx2 >= px2 and vy2 >= py2:
                return v["type"]
        return None

    def process_frame(self, frame) -> list[dict]:
        """Runs detection+OCR on one frame, writes new sightings to DB.
        Returns the list of events logged (useful for live overlay/testing)."""
        events = []
        now = time.time()

        plate_dets = self.plate_detector.detect(frame)
        if not plate_dets:
            return events

        vehicles = self.vehicle_detector.detect(frame)

        for det in plate_dets:
            ocr_result = self.ocr_reader.read(det.crop)
            if ocr_result is None:
                continue
            plate_text, ocr_conf = ocr_result

            if not validate_plate(plate_text):
                # Still log low-confidence/malformed reads at debug level;
                # don't pollute the trajectory DB with garbage plates.
                logger.debug("Rejected malformed plate read: %s", plate_text)
                continue

            if self._already_seen_recently(plate_text, now):
                continue

            vehicle_type = self._match_vehicle_type(det.bbox, vehicles)
            timestamp = datetime.now(timezone.utc).isoformat()

            database.insert_detection(
                plate_number=plate_text,
                camera_id=self.camera_id,
                timestamp=timestamp,
                confidence=det.confidence,
                ocr_confidence=ocr_conf,
                bbox=det.bbox,
                vehicle_type=vehicle_type,
            )
            events.append({
                "plate": plate_text, "camera_id": self.camera_id,
                "timestamp": timestamp, "vehicle_type": vehicle_type,
            })
            logger.info("[%s] detected plate %s (%.2f)", self.camera_id, plate_text, ocr_conf)

        return events

    def run(self):
        """Blocking loop — reads the camera source until it ends/disconnects.
        For RTSP streams this runs indefinitely; for demo video files it
        plays through once, then replays one more time before stopping."""
        source = self.camera_cfg["source"]
        started_at = datetime.now(timezone.utc).isoformat()
        frames_read = 0
        detections_logged = 0
        last_frame_at = None
        last_detection_at = None
        database.upsert_camera_status(self.camera_id, "starting", source=source,
                                       started_at=started_at)
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            database.upsert_camera_status(self.camera_id, "error", source=source,
                                          started_at=started_at, error="Source could not be opened")
            logger.error("[%s] failed to open source: %s", self.camera_id, source)
            return

        frame_idx = 0
        has_looped = False  # tracks whether we've already used our one replay

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    if not has_looped:
                        has_looped = True
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        logger.info("[%s] reached end of file, replaying once", self.camera_id)
                        continue
                    else:
                        logger.info("[%s] stream ended after replay, stopping", self.camera_id)
                        break
                frame_idx += 1
                frames_read += 1
                last_frame_at = datetime.now(timezone.utc).isoformat()
                if frame_idx % self.frame_skip != 0:
                    database.upsert_camera_status(
                        self.camera_id, "online", source=source, started_at=started_at,
                        last_frame_at=last_frame_at, frames_read=frames_read,
                        detections_logged=detections_logged,
                    )
                    continue
                try:
                    events = self.process_frame(frame)
                    detections_logged += len(events)
                    if events:
                        last_detection_at = events[-1]["timestamp"]
                    database.upsert_camera_status(
                        self.camera_id, "online", source=source, started_at=started_at,
                        last_frame_at=last_frame_at, last_detection_at=last_detection_at,
                        frames_read=frames_read, detections_logged=detections_logged,
                    )
                except Exception:
                    database.upsert_camera_status(
                        self.camera_id, "error", source=source, started_at=started_at,
                        last_frame_at=last_frame_at, last_detection_at=last_detection_at,
                        frames_read=frames_read, detections_logged=detections_logged,
                        error=f"Frame processing failed at frame {frame_idx}",
                    )
                    logger.exception("[%s] error processing frame %d", self.camera_id, frame_idx)
        finally:
            cap.release()
            database.upsert_camera_status(
                self.camera_id, "stopped", source=source, started_at=started_at,
                last_frame_at=last_frame_at, last_detection_at=last_detection_at,
                frames_read=frames_read, detections_logged=detections_logged,
            )
