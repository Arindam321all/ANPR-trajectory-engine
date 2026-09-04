-- PostgreSQL equivalent of db/schema.sql. Kept structurally identical so
-- application code and query shapes don't need to know which backend is live.

CREATE TABLE IF NOT EXISTS detections (
    id              BIGSERIAL PRIMARY KEY,
    plate_number    TEXT NOT NULL,
    camera_id       TEXT NOT NULL,
    timestamp       TEXT NOT NULL,        -- ISO 8601 UTC (kept as TEXT to match SQLite exactly)
    confidence      REAL NOT NULL,
    ocr_confidence  REAL NOT NULL,
    bbox_x1         INTEGER,
    bbox_y1         INTEGER,
    bbox_x2         INTEGER,
    bbox_y2         INTEGER,
    vehicle_type    TEXT,
    frame_snapshot  TEXT
);

CREATE INDEX IF NOT EXISTS idx_detections_plate ON detections(plate_number);
CREATE INDEX IF NOT EXISTS idx_detections_camera_time ON detections(camera_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_detections_time ON detections(timestamp);

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

CREATE TABLE IF NOT EXISTS trajectory_legs (
    id                  BIGSERIAL PRIMARY KEY,
    plate_number        TEXT NOT NULL,
    from_camera_id      TEXT NOT NULL,
    to_camera_id        TEXT NOT NULL,
    from_timestamp       TEXT NOT NULL,
    to_timestamp         TEXT NOT NULL,
    distance_km         REAL NOT NULL,
    duration_seconds     REAL NOT NULL,
    speed_kmph          REAL NOT NULL,
    is_overspeed        BOOLEAN DEFAULT FALSE,
    created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_legs_plate ON trajectory_legs(plate_number);
CREATE INDEX IF NOT EXISTS idx_legs_overspeed ON trajectory_legs(is_overspeed);

CREATE TABLE IF NOT EXISTS watchlist (
    plate_number    TEXT PRIMARY KEY,
    reason          TEXT,
    added_at        TEXT
);
