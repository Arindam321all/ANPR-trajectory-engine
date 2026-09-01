-- Every raw plate sighting from any camera lands here.
CREATE TABLE IF NOT EXISTS detections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number    TEXT NOT NULL,
    camera_id       TEXT NOT NULL,
    timestamp       TEXT NOT NULL,        -- ISO 8601 UTC
    confidence      REAL NOT NULL,        -- detector confidence
    ocr_confidence  REAL NOT NULL,        -- OCR confidence
    bbox_x1         INTEGER,
    bbox_y1         INTEGER,
    bbox_x2         INTEGER,
    bbox_y2         INTEGER,
    vehicle_type    TEXT,                 -- car / truck / bike / bus (optional)
    frame_snapshot  TEXT                  -- optional path to saved crop image
);

CREATE INDEX IF NOT EXISTS idx_detections_plate ON detections(plate_number);
CREATE INDEX IF NOT EXISTS idx_detections_camera_time ON detections(camera_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_detections_time ON detections(timestamp);

-- Operational heartbeat published by each camera ingestion worker.
CREATE TABLE IF NOT EXISTS camera_status (
    camera_id           TEXT PRIMARY KEY,
    state               TEXT NOT NULL,
    source              TEXT,
    started_at          TEXT,
    last_frame_at       TEXT,
    last_detection_at   TEXT,
    frames_read         INTEGER DEFAULT 0,
    detections_logged   INTEGER DEFAULT 0,
    error               TEXT,
    updated_at          TEXT NOT NULL
);

-- Precomputed trajectory legs (one row per consecutive camera-to-camera hop
-- for a given plate). Populated by tracking/trajectory_engine.py so the API
-- doesn't have to recompute speed on every request.
CREATE TABLE IF NOT EXISTS trajectory_legs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number        TEXT NOT NULL,
    from_camera_id      TEXT NOT NULL,
    to_camera_id        TEXT NOT NULL,
    from_timestamp      TEXT NOT NULL,
    to_timestamp        TEXT NOT NULL,
    distance_km         REAL NOT NULL,
    duration_seconds     REAL NOT NULL,
    speed_kmph          REAL NOT NULL,
    is_overspeed        INTEGER DEFAULT 0,
    created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_legs_plate ON trajectory_legs(plate_number);
CREATE INDEX IF NOT EXISTS idx_legs_overspeed ON trajectory_legs(is_overspeed);

-- Flagged vehicles (watchlist) for alerting -- optional, used by analytics
-- for stolen-vehicle / wanted-plate style alerts.
CREATE TABLE IF NOT EXISTS watchlist (
    plate_number    TEXT PRIMARY KEY,
    reason          TEXT,
    added_at        TEXT
);
