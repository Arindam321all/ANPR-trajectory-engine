"""
One-off migration: copy every row out of the existing SQLite database into a
Postgres database, so switching database.type from sqlite to postgres in
config.yaml doesn't lose whatever has already been recorded.

Usage:
    1. In config.yaml, set the [database] postgres fields (host/name/user/...)
       -- you can leave `type: sqlite` for now, this script reads that
       separately.
    2. Make sure the Postgres schema exists:
           python -c "from db.backends.postgres_backend import init_db; init_db()"
    3. Run:
           python scripts/migrate_sqlite_to_postgres.py [--sqlite-path city_anpr.db]
    4. Only after this completes cleanly, flip config.yaml to `type: postgres`.

Safe to re-run: uses INSERT ... ON CONFLICT DO NOTHING / matches existing
primary keys, so already-migrated rows are skipped rather than duplicated.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # so `db`/`config_loader` import cleanly

from db.backends import postgres_backend as pg  # noqa: E402


TABLES = ["detections", "camera_status", "trajectory_legs", "watchlist"]


def _rows(sqlite_conn, table):
    sqlite_conn.row_factory = sqlite3.Row
    cur = sqlite_conn.execute(f"SELECT * FROM {table}")
    return [dict(r) for r in cur.fetchall()]


def migrate(sqlite_path: str, batch_size: int = 1000):
    sconn = sqlite3.connect(sqlite_path)
    pg.init_db()  # ensure target schema exists

    for table in TABLES:
        rows = _rows(sconn, table)
        if not rows:
            print(f"[migrate] {table}: 0 rows, skipping")
            continue

        cols = list(rows[0].keys())
        col_list = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))

        # id columns are auto-generated on the Postgres side for detections/
        # trajectory_legs; keep the original id to preserve ordering/FKs if
        # any downstream code relies on it, but don't fail if it collides.
        conflict_col = {
            "detections": "id",
            "trajectory_legs": "id",
            "camera_status": "camera_id",
            "watchlist": "plate_number",
        }[table]

        with pg.cursor() as cur:
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                for row in batch:
                    values = [row[c] for c in cols]
                    cur.execute(
                        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
                        f"ON CONFLICT ({conflict_col}) DO NOTHING",
                        values,
                    )
        print(f"[migrate] {table}: migrated {len(rows)} rows")

    # detections/trajectory_legs kept their original SQLite ids, so bump the
    # Postgres sequences past the max id we just inserted -- otherwise the
    # next auto-generated insert could collide with a migrated row.
    with pg.cursor() as cur:
        for table in ("detections", "trajectory_legs"):
            cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
            )

    sconn.close()
    print("[migrate] done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-path", default="city_anpr.db")
    args = parser.parse_args()
    migrate(args.sqlite_path)
