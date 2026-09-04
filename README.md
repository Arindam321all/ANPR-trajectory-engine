# PS127 — City-Wide AI Engine for Multi-Camera ANPR Trajectory Tracking & Urban Traffic Analytics

A city-scale pipeline that:

1. **Detects & reads license plates** from multiple camera feeds (`detection/`)
2. **Tracks vehicles within a single camera** view (`tracking/camera_tracker.py`)
3. **Links a vehicle's plate across different cameras** across the city into a single trajectory, ordered by time (`tracking/trajectory_engine.py`)
4. **Computes traffic analytics**: inter-camera travel speed, congestion levels, hotspot heatmaps, overspeed flags, route reconstruction (`analytics/traffic_analytics.py`)
5. **Evaluates traffic rules and sends alerts**: watchlist, overspeed, signal jumps, restricted lanes, route deviation, wrong-way and temporary one-way violations (`alerting/`)
6. **Serves everything over a REST API** (`api/main.py`) + a lightweight live dashboard (`dashboard/index.html`)

## Architecture

```
 Camera 1 (RTSP/video) ─┐
 Camera 2 (RTSP/video) ─┼─▶ CameraTracker (per camera, own process/thread)
 Camera N (RTSP/video) ─┘        │
                                  │  YOLO plate detector ─▶ EasyOCR reader
                                  │  (detection/plate_detector.py, ocr_reader.py)
                                  ▼
                         SQLite / Postgres  (db/database.py)
                          "detections" table
                                  │
                                  ▼
                    TrajectoryEngine  (tracking/trajectory_engine.py)
                    groups detections by plate_number across cameras,
                    orders by timestamp -> builds a Trajectory
                                  │
                                  ▼
                    TrafficAnalytics (analytics/traffic_analytics.py)
                    speed between camera pairs, congestion/min,
                    heatmap grid, overspeed & loitering flags
                                  │
                                  ▼
                       FastAPI (api/main.py)  ──▶  dashboard/index.html
```

## Install

```bash
pip install -r requirements.txt
```

GPU is strongly recommended for real-time YOLO+OCR (works on CPU too, just slower).

## Configure cameras

Edit `config.yaml` — each camera needs an id, a video source (file path or RTSP URL),
its lat/lon, and the road distance (in km) to its directly-connected neighbor cameras
(used for speed calculation between consecutive sightings).

## Run

```bash
# 1. Initialize the database
python -c "from db.database import init_db; init_db()"

# 2. Start ingestion for all cameras defined in config.yaml
python main.py

# 3. In another terminal, start the API + dashboard
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Then open `dashboard/index.html` (served by the API at `/`) in a browser.

## Key API endpoints

| Endpoint | Description |
|---|---|
| `GET /detections?plate=XX00XX0000` | Raw detection events for a plate |
| `GET /trajectory/{plate}` | Full cross-camera trajectory with computed speeds |
| `GET /analytics/congestion` | Vehicles/minute per camera, last N minutes |
| `GET /analytics/heatmap` | Grid of detection density for map overlay |
| `GET /analytics/route-congestion` | Camera-to-camera routes colored green, orange, or red by traffic volume and speed |
| `GET /analytics/overspeed` | List of trajectory legs exceeding speed limit |
| `GET /analytics/summary` | City-wide dashboard summary stats |
| `GET /alerts?window_minutes=60` | Recent rule violations and notification status |

## Configure enforcement rules

The `alerting.rules` section in `config.yaml` enables or disables each rule.
Add camera metadata where it applies: `allowed_next_cameras` for directed route
checks, `temporary_one_way_to` for temporary one-way enforcement, `lane_type`
(`two_wheeler` or `non_motorised`) with optional `restricted_vehicle_types`, and
`allowed_directions` for direction checks.

Watchlist alerts are automatic after `POST /watchlist/add`. Overspeed alerts use
confirmed routed distance and the existing speed-limit calculation. Signal-jump,
wrong-way, and per-frame lane alerts require a perception adapter to call
`CameraTracker.process_frame(frame, event_context={...})` with `signal_state`,
`crossed_stop_line`, `travel_direction`, and/or `lane_type`. OCR alone cannot
prove those violations.

Set `alerting.notifications.webhook_url` to deliver JSON alerts to an HTTP
receiver. Logging remains enabled by default, and a failed webhook never stops
camera ingestion.

## Notes on production hardening

- Swap SQLite for Postgres/TimescaleDB at city scale (see `db/database.py` — the SQL is
  standard enough to port directly; only the connection string changes).
- Replace the demo YOLO plate model with a plate-detection model fine-tuned on your
  region's plate formats (Indian/EU/US plates differ in aspect ratio & font).
- Add plate-format validation regex per state/country in `ocr_reader.py::validate_plate`.
- For real deployments, run one `CameraTracker` per process (see `main.py`) so a stalled
  RTSP stream doesn't block others; consider Celery/Kafka instead of direct DB writes at
  very high camera counts.
