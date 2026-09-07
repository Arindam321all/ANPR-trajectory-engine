"""
Backend-selecting facade. Every other module in the repo does

    from db.database import insert_detection, get_detections_for_plate, ...

and keeps working unchanged no matter which backend is configured -- this
file just re-exports the real implementation from db/backends/.

Pick the backend in config.yaml:

    database:
      type: sqlite            # default, unchanged from before
      path: "city_anpr.db"

    database:
      type: postgres           # new, for large-scale / production deployments
      host: "localhost"
      port: 5432
      name: "anpr"
      user: "anpr"
      password: "changeme"     # prefer an env-var driven dsn: below instead
      # dsn: "${DATABASE_URL}"  # optional, overrides host/port/name/user/password
      pool_min: 2
      pool_max: 20

Why: SQLite is a single file with one effective writer, so ingestion from
several camera threads plus concurrent API reads becomes a bottleneck as
detection volume grows (this was already flagged in the README's production
notes). Postgres gives real concurrent writers, connection pooling, and
scales to the "large amount of data" a multi-camera, city-wide deployment
produces, without changing a single call site elsewhere in the codebase.
"""
from config_loader import get_config


def _backend_name() -> str:
    return get_config().get("database", {}).get("type", "sqlite").lower()


_name = _backend_name()
if _name == "postgres":
    from db.backends.postgres_backend import *  # noqa: F401,F403
elif _name == "sqlite":
    from db.backends.sqlite_backend import *  # noqa: F401,F403
else:
    raise ValueError(
        f"Unknown database.type '{_name}' in config.yaml -- expected 'sqlite' or 'postgres'"
    )
