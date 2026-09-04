"""
Thin SQLite data-access layer. Every write/read the rest of the system needs
goes through here, so swapping SQLite for Postgres later only means changing
this file's connection logic (the SQL below is written to be portable).
"""
import sqlite3
import threading
import json
from pathlib import Path
from contextlib import contextmanager

from config_loader import get_config

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_local = threading.local()  # one connection per thread (safe for multi-camera threads)


def _db_path() -> str:
    return get_config()["database"]["path"]


def get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn"):
        _local.conn = sqlite3.connect(_db_path(), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL;")  # allow concurrent readers+writer
    return _local.conn


@contextmanager
def cursor():
    conn = get_conn()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def init_db():
    conn = sqlite3.connect(_db_path())
    with open(_SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    # Keep databases created by older versions usable after schema updates.
    detection_columns = {row[1] for row in conn.execute("PRAGMA table_info(detections)")}
    for column, definition in {
        "signal_state": "TEXT",
        "crossed_stop_line": "INTEGER",
        "travel_direction": "TEXT",
        "lane_type": "TEXT",
    }.items():
        if column not in detection_columns:
            conn.execute(f"ALTER TABLE detections ADD COLUMN {column} {definition}")
    conn.commit()
    conn.close()
    print(f"[db] initialized at {_db_path()}")


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------

def insert_detection(plate_number: str, camera_id: str, timestamp: str,
                      confidence: float, ocr_confidence: float,
                      bbox: tuple | None = None, vehicle_type: str | None = None,
                      frame_snapshot: str | None = None,
                      signal_state: str | None = None,
                      crossed_stop_line: bool | None = None,
                      travel_direction: str | None = None,
                      lane_type: str | None = None) -> int:
    bbox = bbox or (None, None, None, None)
    with cursor() as cur:
        cur.execute(
            """INSERT INTO detections
                             (plate_number, camera_id, timestamp, confidence, ocr_confidence,
                                bbox_x1, bbox_y1, bbox_x2, bbox_y2, vehicle_type, frame_snapshot,
                                signal_state, crossed_stop_line, travel_direction, lane_type)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (plate_number, camera_id, timestamp, confidence, ocr_confidence,
                         *bbox, vehicle_type, frame_snapshot, signal_state,
                         None if crossed_stop_line is None else int(crossed_stop_line),
                         travel_direction, lane_type),
        )
        return cur.lastrowid


def upsert_camera_status(camera_id: str, state: str, source: str | None = None,
                         started_at: str | None = None, last_frame_at: str | None = None,
                         last_detection_at: str | None = None, frames_read: int = 0,
                         detections_logged: int = 0, error: str | None = None):
    from datetime import datetime, timezone
    updated_at = datetime.now(timezone.utc).isoformat()
    with cursor() as cur:
        cur.execute(
            """INSERT INTO camera_status
               (camera_id, state, source, started_at, last_frame_at, last_detection_at,
                frames_read, detections_logged, error, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(camera_id) DO UPDATE SET
                 state=excluded.state, source=COALESCE(excluded.source, camera_status.source),
                 started_at=COALESCE(excluded.started_at, camera_status.started_at),
                 last_frame_at=COALESCE(excluded.last_frame_at, camera_status.last_frame_at),
                 last_detection_at=COALESCE(excluded.last_detection_at, camera_status.last_detection_at),
                 frames_read=excluded.frames_read, detections_logged=excluded.detections_logged,
                 error=excluded.error, updated_at=excluded.updated_at""",
            (camera_id, state, source, started_at, last_frame_at, last_detection_at,
             frames_read, detections_logged, error, updated_at),
        )


def get_camera_statuses() -> list[sqlite3.Row]:
    with cursor() as cur:
        cur.execute("SELECT * FROM camera_status ORDER BY camera_id")
        return cur.fetchall()


def insert_trajectory_leg(plate_number: str, from_camera_id: str, to_camera_id: str,
                           from_timestamp: str, to_timestamp: str, distance_km: float,
                           duration_seconds: float, speed_kmph: float, is_overspeed: bool):
    from datetime import datetime, timezone
    with cursor() as cur:
        cur.execute(
            """INSERT INTO trajectory_legs
               (plate_number, from_camera_id, to_camera_id, from_timestamp, to_timestamp,
                distance_km, duration_seconds, speed_kmph, is_overspeed, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (plate_number, from_camera_id, to_camera_id, from_timestamp, to_timestamp,
             distance_km, duration_seconds, speed_kmph, int(is_overspeed),
             datetime.now(timezone.utc).isoformat()),
        )


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------

def get_detections_for_plate(plate_number: str) -> list[sqlite3.Row]:
    with cursor() as cur:
        cur.execute(
            "SELECT * FROM detections WHERE plate_number = ? ORDER BY timestamp ASC",
            (plate_number,),
        )
        return cur.fetchall()


def get_recent_detections(camera_id: str | None, since_iso: str) -> list[sqlite3.Row]:
    with cursor() as cur:
        if camera_id:
            cur.execute(
                "SELECT * FROM detections WHERE camera_id = ? AND timestamp >= ? "
                "ORDER BY timestamp ASC", (camera_id, since_iso),
            )
        else:
            cur.execute(
                "SELECT * FROM detections WHERE timestamp >= ? ORDER BY timestamp ASC",
                (since_iso,),
            )
        return cur.fetchall()


def get_all_recent_for_heatmap(since_iso: str) -> list[sqlite3.Row]:
    with cursor() as cur:
        cur.execute(
            "SELECT camera_id, COUNT(*) as cnt FROM detections WHERE timestamp >= ? "
            "GROUP BY camera_id", (since_iso,),
        )
        return cur.fetchall()


def get_trajectory_legs_for_plate(plate_number: str) -> list[sqlite3.Row]:
    with cursor() as cur:
        cur.execute(
            "SELECT * FROM trajectory_legs WHERE plate_number = ? ORDER BY from_timestamp ASC",
            (plate_number,),
        )
        return cur.fetchall()


def get_recent_trajectory_legs(since_iso: str) -> list[sqlite3.Row]:
    with cursor() as cur:
        cur.execute(
            "SELECT * FROM trajectory_legs WHERE from_timestamp >= ?",
            (since_iso,)
        )
        return cur.fetchall()


def get_overspeed_legs(limit: int = 100) -> list[sqlite3.Row]:
    with cursor() as cur:
        cur.execute(
            "SELECT * FROM trajectory_legs WHERE is_overspeed = 1 "
            "ORDER BY created_at DESC LIMIT ?", (limit,),
        )
        return cur.fetchall()


def get_distinct_plates_since(since_iso: str) -> list[str]:
    with cursor() as cur:
        cur.execute(
            "SELECT DISTINCT plate_number FROM detections WHERE timestamp >= ?",
            (since_iso,),
        )
        return [r["plate_number"] for r in cur.fetchall()]


def is_watchlisted(plate_number: str) -> sqlite3.Row | None:
    with cursor() as cur:
        cur.execute("SELECT * FROM watchlist WHERE plate_number = ?", (plate_number,))
        return cur.fetchone()


def add_to_watchlist(plate_number: str, reason: str):
    from datetime import datetime, timezone
    with cursor() as cur:
        cur.execute(
            "INSERT OR REPLACE INTO watchlist (plate_number, reason, added_at) VALUES (?, ?, ?)",
            (plate_number, reason, datetime.now(timezone.utc).isoformat()),
        )


def insert_alert(fingerprint: str, alert_type: str, severity: str,
                 plate_number: str | None, camera_id: str | None,
                 from_camera_id: str | None, to_camera_id: str | None,
                 occurred_at: str, message: str, details: dict) -> tuple[int, bool]:
    """Insert one alert once. Returns (id, was_created)."""
    from datetime import datetime, timezone
    with cursor() as cur:
        cur.execute(
            """INSERT OR IGNORE INTO alerts
               (fingerprint, alert_type, severity, plate_number, camera_id,
                from_camera_id, to_camera_id, occurred_at, message, details_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fingerprint, alert_type, severity, plate_number, camera_id,
             from_camera_id, to_camera_id, occurred_at, message,
             json.dumps(details, default=str), datetime.now(timezone.utc).isoformat()),
        )
        if cur.rowcount == 0:
            cur.execute("SELECT id FROM alerts WHERE fingerprint = ?", (fingerprint,))
            return cur.fetchone()["id"], False
        return cur.lastrowid, True


def mark_alert_notified(alert_id: int):
    with cursor() as cur:
        cur.execute("UPDATE alerts SET notified = 1 WHERE id = ?", (alert_id,))


def get_recent_alerts(since_iso: str, alert_type: str | None = None,
                      limit: int = 100) -> list[sqlite3.Row]:
    with cursor() as cur:
        if alert_type:
            cur.execute(
                "SELECT * FROM alerts WHERE occurred_at >= ? AND alert_type = ? "
                "ORDER BY occurred_at DESC LIMIT ?", (since_iso, alert_type, limit))
        else:
            cur.execute(
                "SELECT * FROM alerts WHERE occurred_at >= ? ORDER BY occurred_at DESC LIMIT ?",
                (since_iso, limit))
        return cur.fetchall()
