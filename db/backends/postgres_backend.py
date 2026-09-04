"""
PostgreSQL data-access layer. Drop-in replacement for sqlite_backend.py --
every function name, argument list, and return shape (list of dict-like rows)
matches exactly, so tracking/, analytics/, and api/ never need to know which
backend is active.

Uses a process-wide threaded connection pool (psycopg2.pool.ThreadedConnectionPool)
so it's safe to call from multiple camera-ingestion threads plus the FastAPI
request-handling threads at once, and so we don't pay a new-TCP-connection cost
on every insert -- this is the main reason SQLite falls over at city scale
(one writer, file locks) while Postgres does not.

Rows are returned as psycopg2.extras.RealDictRow, which supports row["col"]
access exactly like sqlite3.Row. It does NOT support integer indexing
(row[0]) -- if any calling code relies on that, switch RealDictCursor to a
plain cursor and adjust, but nothing in this repo does at the time this was
written.
"""
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from config_loader import get_config

_SCHEMA_PATH = Path(__file__).parent.parent / "schema_postgres.sql"

_pool: ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _pg_config() -> dict:
    return get_config()["database"]


def _dsn() -> str:
    cfg = _pg_config()
    # Prefer an explicit DSN/URL if given (e.g. from an env var in config.yaml),
    # otherwise build one from discrete fields.
    if cfg.get("dsn"):
        return cfg["dsn"]
    return (
        f"host={cfg.get('host', 'localhost')} "
        f"port={cfg.get('port', 5432)} "
        f"dbname={cfg['name']} "
        f"user={cfg['user']} "
        f"password={cfg.get('password', '')}"
    )


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:  # re-check inside the lock
                cfg = _pg_config()
                _pool = ThreadedConnectionPool(
                    minconn=cfg.get("pool_min", 2),
                    maxconn=cfg.get("pool_max", 20),
                    dsn=_dsn(),
                )
    return _pool


@contextmanager
def cursor():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    finally:
        pool.putconn(conn)


def init_db():
    """Creates tables/indexes if they don't exist. Safe to run repeatedly."""
    conn = psycopg2.connect(_dsn())
    try:
        with conn.cursor() as cur, open(_SCHEMA_PATH, "r") as f:
            cur.execute(f.read())
        conn.commit()
    finally:
        conn.close()
    print(f"[db] postgres schema ensured at {_pg_config().get('host', 'localhost')}/{_pg_config()['name']}")


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------

def insert_detection(plate_number: str, camera_id: str, timestamp: str,
                      confidence: float, ocr_confidence: float,
                      bbox: tuple | None = None, vehicle_type: str | None = None,
                      frame_snapshot: str | None = None) -> int:
    bbox = bbox or (None, None, None, None)
    with cursor() as cur:
        cur.execute(
            """INSERT INTO detections
               (plate_number, camera_id, timestamp, confidence, ocr_confidence,
                bbox_x1, bbox_y1, bbox_x2, bbox_y2, vehicle_type, frame_snapshot)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (plate_number, camera_id, timestamp, confidence, ocr_confidence,
             *bbox, vehicle_type, frame_snapshot),
        )
        return cur.fetchone()["id"]


def upsert_camera_status(camera_id: str, state: str, source: str | None = None,
                          started_at: str | None = None, last_frame_at: str | None = None,
                          last_detection_at: str | None = None, frames_read: int = 0,
                          detections_logged: int = 0, error: str | None = None):
    updated_at = datetime.now(timezone.utc).isoformat()
    with cursor() as cur:
        cur.execute(
            """INSERT INTO camera_status
               (camera_id, state, source, started_at, last_frame_at, last_detection_at,
                frames_read, detections_logged, error, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (camera_id) DO UPDATE SET
                 state=EXCLUDED.state, source=COALESCE(EXCLUDED.source, camera_status.source),
                 started_at=COALESCE(EXCLUDED.started_at, camera_status.started_at),
                 last_frame_at=COALESCE(EXCLUDED.last_frame_at, camera_status.last_frame_at),
                 last_detection_at=COALESCE(EXCLUDED.last_detection_at, camera_status.last_detection_at),
                 frames_read=EXCLUDED.frames_read, detections_logged=EXCLUDED.detections_logged,
                 error=EXCLUDED.error, updated_at=EXCLUDED.updated_at""",
            (camera_id, state, source, started_at, last_frame_at, last_detection_at,
             frames_read, detections_logged, error, updated_at),
        )


def get_camera_statuses() -> list:
    with cursor() as cur:
        cur.execute("SELECT * FROM camera_status ORDER BY camera_id")
        return cur.fetchall()


def insert_trajectory_leg(plate_number: str, from_camera_id: str, to_camera_id: str,
                           from_timestamp: str, to_timestamp: str, distance_km: float,
                           duration_seconds: float, speed_kmph: float, is_overspeed: bool):
    with cursor() as cur:
        cur.execute(
            """INSERT INTO trajectory_legs
               (plate_number, from_camera_id, to_camera_id, from_timestamp, to_timestamp,
                distance_km, duration_seconds, speed_kmph, is_overspeed, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (plate_number, from_camera_id, to_camera_id, from_timestamp, to_timestamp,
             distance_km, duration_seconds, speed_kmph, bool(is_overspeed),
             datetime.now(timezone.utc).isoformat()),
        )


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------

def get_detections_for_plate(plate_number: str) -> list:
    with cursor() as cur:
        cur.execute(
            "SELECT * FROM detections WHERE plate_number = %s ORDER BY timestamp ASC",
            (plate_number,),
        )
        return cur.fetchall()


def get_recent_detections(camera_id: str | None, since_iso: str) -> list:
    with cursor() as cur:
        if camera_id:
            cur.execute(
                "SELECT * FROM detections WHERE camera_id = %s AND timestamp >= %s "
                "ORDER BY timestamp ASC", (camera_id, since_iso),
            )
        else:
            cur.execute(
                "SELECT * FROM detections WHERE timestamp >= %s ORDER BY timestamp ASC",
                (since_iso,),
            )
        return cur.fetchall()


def get_all_recent_for_heatmap(since_iso: str) -> list:
    with cursor() as cur:
        cur.execute(
            "SELECT camera_id, COUNT(*) as cnt FROM detections WHERE timestamp >= %s "
            "GROUP BY camera_id", (since_iso,),
        )
        return cur.fetchall()


def get_trajectory_legs_for_plate(plate_number: str) -> list:
    with cursor() as cur:
        cur.execute(
            "SELECT * FROM trajectory_legs WHERE plate_number = %s ORDER BY from_timestamp ASC",
            (plate_number,),
        )
        return cur.fetchall()


def get_recent_trajectory_legs(since_iso: str) -> list:
    with cursor() as cur:
        cur.execute(
            "SELECT * FROM trajectory_legs WHERE from_timestamp >= %s",
            (since_iso,)
        )
        return cur.fetchall()


def get_overspeed_legs(limit: int = 100) -> list:
    with cursor() as cur:
        cur.execute(
            "SELECT * FROM trajectory_legs WHERE is_overspeed = TRUE "
            "ORDER BY created_at DESC LIMIT %s", (limit,),
        )
        return cur.fetchall()


def get_distinct_plates_since(since_iso: str) -> list[str]:
    with cursor() as cur:
        cur.execute(
            "SELECT DISTINCT plate_number FROM detections WHERE timestamp >= %s",
            (since_iso,),
        )
        return [r["plate_number"] for r in cur.fetchall()]


def is_watchlisted(plate_number: str):
    with cursor() as cur:
        cur.execute("SELECT * FROM watchlist WHERE plate_number = %s", (plate_number,))
        return cur.fetchone()


def add_to_watchlist(plate_number: str, reason: str):
    with cursor() as cur:
        cur.execute(
            """INSERT INTO watchlist (plate_number, reason, added_at) VALUES (%s, %s, %s)
               ON CONFLICT (plate_number) DO UPDATE SET
                 reason = EXCLUDED.reason, added_at = EXCLUDED.added_at""",
            (plate_number, reason, datetime.now(timezone.utc).isoformat()),
        )
