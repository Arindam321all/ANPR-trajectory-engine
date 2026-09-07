# Trajectra — Streamlit Frontend

A Streamlit dashboard for the ANPR-trajectory-engine FastAPI backend
(https://github.com/debanjanNiyogi/ANPR-trajectory-engine), replacing the
React landing page with a functional operational UI.

## Pages

- **Overview** — city-wide stats, congestion table, detection heatmap (pydeck),
  route congestion, overspeed incidents, and a button to force-rebuild trajectories.
- **Cameras** — camera list with live ingestion status (state, frames read,
  detections logged), a map of camera locations, and a form to upload a video
  file for a given camera.
- **Vehicle Lookup** — search a plate number to see its cross-camera trajectory,
  raw detection events, and watchlist status.
- **Alerts** — recent rule-violation alerts with filters, plus a manual
  auto-refresh button.
- **Watchlist** — add a plate to the watchlist or check if one is already on it.

## Setup

```bash
cd streamlit_frontend
pip install -r requirements.txt
```

(Do this inside the same virtual environment as the backend, or its own —
either works, since this only needs `streamlit`, `requests`, `pandas`, `pydeck`.)

## Run

**1. Start the backend first** (from the `backend/` folder):
```bash
python main.py                                     # camera ingestion (terminal 1)
uvicorn api.main:app --host 0.0.0.0 --port 8000     # API (terminal 2)
```

**2. Then start this app** (terminal 3):
```bash
cd streamlit_frontend
streamlit run app.py
```

Streamlit will open at `http://localhost:8501`. The backend URL defaults to
`http://localhost:8000` — you can override it via the sidebar text box at
runtime, or by setting the `API_BASE_URL` environment variable before
launching (`$env:API_BASE_URL="http://..."` on PowerShell, or copy
`.env.example` to `.env` and export it).

## Notes

- Every page calls the backend live — there's no offline/static fallback like
  the React version had, since this is meant as an operator dashboard rather
  than a marketing page. If the backend isn't reachable, pages show a clear
  error instead of stale data.
- The sidebar shows a "Backend live" / "Backend offline" indicator based on
  a `/cameras` ping.
