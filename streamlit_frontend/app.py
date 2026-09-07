"""
Trajectra — Streamlit dashboard for the ANPR-trajectory-engine backend.

Run the FastAPI backend first (from the backend/ folder):
    uvicorn api.main:app --host 0.0.0.0 --port 8000

Then run this app:
    streamlit run app.py

Configure the backend URL either via the sidebar, or by setting the
API_BASE_URL environment variable / a .env file (see .env.example).
"""
import os
import time

import pandas as pd
import pydeck as pdk
import requests
import streamlit as st

# --------------------------------------------------------------------------
# Config & API helpers
# --------------------------------------------------------------------------

st.set_page_config(page_title="Trajectra — ANPR Traffic Intelligence", layout="wide")

DEFAULT_API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

if "api_base_url" not in st.session_state:
    st.session_state.api_base_url = DEFAULT_API_BASE_URL


def api_get(path: str, params: dict | None = None, timeout: int = 10):
    """GET against the backend. Returns (data, error_message)."""
    url = st.session_state.api_base_url.rstrip("/") + path
    try:
        res = requests.get(url, params=params or {}, timeout=timeout)
        res.raise_for_status()
        return res.json(), None
    except requests.exceptions.ConnectionError:
        return None, f"Could not reach backend at {st.session_state.api_base_url}. Is uvicorn running?"
    except requests.exceptions.HTTPError as e:
        detail = ""
        try:
            detail = res.json().get("detail", "")
        except Exception:
            pass
        return None, f"{e} {detail}"
    except Exception as e:
        return None, str(e)


def api_post(path: str, params: dict | None = None, timeout: int = 10):
    url = st.session_state.api_base_url.rstrip("/") + path
    try:
        res = requests.post(url, params=params or {}, timeout=timeout)
        res.raise_for_status()
        return res.json(), None
    except requests.exceptions.ConnectionError:
        return None, f"Could not reach backend at {st.session_state.api_base_url}. Is uvicorn running?"
    except requests.exceptions.HTTPError as e:
        detail = ""
        try:
            detail = res.json().get("detail", "")
        except Exception:
            pass
        return None, f"{e} {detail}"
    except Exception as e:
        return None, str(e)


# --------------------------------------------------------------------------
# Sidebar — connection + nav
# --------------------------------------------------------------------------

with st.sidebar:
    st.title("🚦 Trajectra")
    st.caption("ANPR Trajectory & Traffic Analytics")

    st.session_state.api_base_url = st.text_input(
        "Backend API URL", value=st.session_state.api_base_url
    )

    page = st.radio(
        "Navigate",
        ["Overview", "Cameras", "Vehicle Lookup", "Alerts", "Watchlist"],
        label_visibility="collapsed",
    )

    st.divider()
    _, ping_err = api_get("/cameras")
    if ping_err:
        st.error("Backend offline")
    else:
        st.success("Backend live")

# --------------------------------------------------------------------------
# Overview page
# --------------------------------------------------------------------------

if page == "Overview":
    st.header("City Intelligence Overview")

    window = st.slider("Window (minutes)", 5, 1440, 60, step=5)

    summary, err = api_get("/analytics/summary", {"window_minutes": window})
    if err:
        st.error(err)
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Unique vehicles seen", summary.get("unique_vehicles_seen", "—"))
        c2.metric("Total cameras", summary.get("total_cameras", "—"))
        c3.metric(
            "Busiest camera",
            summary.get("busiest_camera") or "—",
            f"{summary.get('busiest_camera_rate_per_min', 0)}/min",
        )
        c4.metric("Overspeed incidents", summary.get("overspeed_incidents_total", "—"))

        st.subheader("Congestion by camera")
        congestion = summary.get("congestion_by_camera", [])
        if congestion:
            df = pd.DataFrame(congestion)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No congestion data for this window yet.")

    st.subheader("Detection heatmap")
    heatmap, hm_err = api_get("/analytics/heatmap", {"window_minutes": window})
    if hm_err:
        st.error(hm_err)
    elif heatmap:
        df_hm = pd.DataFrame(heatmap)
        layer = pdk.Layer(
            "HeatmapLayer",
            data=df_hm,
            get_position=["lon", "lat"],
            get_weight="intensity",
            radius_pixels=60,
        )
        view_state = pdk.ViewState(
            latitude=df_hm["lat"].mean(),
            longitude=df_hm["lon"].mean(),
            zoom=11,
        )
        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state))
    else:
        st.info("No detections in this window to plot.")

    st.subheader("Route congestion")
    routes, r_err = api_get("/analytics/route-congestion", {"window_minutes": window})
    if r_err:
        st.error(r_err)
    elif routes:
        df_r = pd.DataFrame(routes)
        show_cols = [c for c in df_r.columns if c != "route_coords"]
        st.dataframe(df_r[show_cols], use_container_width=True, hide_index=True)
    else:
        st.info("No route data for this window yet.")

    with st.expander("Overspeed incidents"):
        overspeed, os_err = api_get("/analytics/overspeed", {"limit": 100})
        if os_err:
            st.error(os_err)
        elif overspeed:
            st.dataframe(pd.DataFrame(overspeed), use_container_width=True, hide_index=True)
        else:
            st.info("No overspeed incidents recorded.")

    if st.button("🔄 Rebuild all trajectories"):
        result, rb_err = api_post("/trajectory/rebuild-all", {"since_minutes": 1440})
        if rb_err:
            st.error(rb_err)
        else:
            st.success(f"Rebuilt: {result}")

# --------------------------------------------------------------------------
# Cameras page
# --------------------------------------------------------------------------

elif page == "Cameras":
    st.header("Camera Network")

    cameras, err = api_get("/cameras")
    ingestion, ing_err = api_get("/ingestion/status")

    if err:
        st.error(err)
    else:
        df_cam = pd.DataFrame(cameras)
        if not df_cam.empty and ingestion:
            status_map = {row["camera_id"]: row for row in ingestion}
            df_cam["state"] = df_cam["id"].map(lambda cid: status_map.get(cid, {}).get("state", "unknown"))
            df_cam["frames_read"] = df_cam["id"].map(lambda cid: status_map.get(cid, {}).get("frames_read", 0))
            df_cam["detections_logged"] = df_cam["id"].map(
                lambda cid: status_map.get(cid, {}).get("detections_logged", 0)
            )

        st.dataframe(df_cam, use_container_width=True, hide_index=True)

        if not df_cam.empty and {"lat", "lon"}.issubset(df_cam.columns):
            st.map(df_cam.rename(columns={"lat": "latitude", "lon": "longitude"}))

    st.subheader("Upload a video for processing")
    with st.form("upload_video"):
        camera_id = st.text_input("Camera ID (must exist in config.yaml)")
        video_file = st.file_uploader("Video file", type=["mp4", "avi", "mov", "mkv", "webm"])
        submitted = st.form_submit_button("Upload & process")
        if submitted and video_file and camera_id:
            url = st.session_state.api_base_url.rstrip("/") + "/uploads/videos"
            try:
                res = requests.post(
                    url,
                    data={"camera_id": camera_id},
                    files={"file": (video_file.name, video_file.getvalue())},
                    timeout=30,
                )
                res.raise_for_status()
                st.success(f"Upload accepted: {res.json()}")
            except Exception as e:
                st.error(f"Upload failed: {e}")

# --------------------------------------------------------------------------
# Vehicle Lookup page
# --------------------------------------------------------------------------

elif page == "Vehicle Lookup":
    st.header("Vehicle Lookup")

    plate = st.text_input("Plate number", placeholder="e.g. KA05MH1234").strip().upper()

    if plate:
        tab1, tab2, tab3 = st.tabs(["Trajectory", "Raw detections", "Watchlist"])

        with tab1:
            rebuild = st.checkbox("Force rebuild trajectory", value=False)
            traj, err = api_get(f"/trajectory/{plate}", {"rebuild": rebuild})
            if err:
                st.error(err)
            elif traj:
                if "legs" in traj:
                    st.write(f"**{len(traj['legs'])} leg(s)** for {traj['plate_number']}")
                    st.dataframe(
                        pd.DataFrame(traj["legs"]).drop(columns=["route_coords"], errors="ignore"),
                        use_container_width=True,
                        hide_index=True,
                    )
                    loitering = traj.get("loitering")
                    if loitering:
                        st.warning(f"Loitering signal: {loitering}")
                else:
                    st.info(traj.get("message", "No trajectory yet."))
                    if "detections" in traj:
                        st.dataframe(pd.DataFrame(traj["detections"]), use_container_width=True, hide_index=True)

        with tab2:
            detections, d_err = api_get("/detections", {"plate": plate})
            if d_err:
                st.error(d_err)
            elif detections:
                st.dataframe(pd.DataFrame(detections), use_container_width=True, hide_index=True)

        with tab3:
            wl, wl_err = api_get(f"/watchlist/check/{plate}")
            if wl_err:
                st.error(wl_err)
            elif wl:
                if wl["watchlisted"]:
                    st.error(f"⚠️ WATCHLISTED — reason: {wl['reason']}")
                else:
                    st.success("Not on watchlist")
    else:
        st.info("Enter a plate number above to look it up.")

# --------------------------------------------------------------------------
# Alerts page
# --------------------------------------------------------------------------

elif page == "Alerts":
    st.header("Recent Alerts")

    col1, col2, col3 = st.columns(3)
    window = col1.number_input("Window (minutes)", min_value=1, value=60)
    alert_type = col2.text_input("Alert type filter (optional)")
    limit = col3.number_input("Limit", min_value=1, max_value=1000, value=100)

    alerts, err = api_get(
        "/alerts",
        {"window_minutes": window, "alert_type": alert_type or None, "limit": limit},
    )
    if err:
        st.error(err)
    elif alerts:
        df_a = pd.DataFrame(alerts)
        st.dataframe(df_a, use_container_width=True, hide_index=True)
    else:
        st.info("No alerts in this window.")

    if st.button("Auto-refresh every 15s"):
        time.sleep(15)
        st.rerun()

# --------------------------------------------------------------------------
# Watchlist page
# --------------------------------------------------------------------------

elif page == "Watchlist":
    st.header("Watchlist")

    st.subheader("Add a plate")
    with st.form("add_watchlist"):
        wl_plate = st.text_input("Plate number").strip().upper()
        reason = st.text_input("Reason", value="unspecified")
        submitted = st.form_submit_button("Add to watchlist")
        if submitted and wl_plate:
            result, err = api_post("/watchlist/add", {"plate": wl_plate, "reason": reason})
            if err:
                st.error(err)
            else:
                st.success(f"Added: {result}")

    st.subheader("Check a plate")
    check_plate = st.text_input("Plate to check", key="check_plate").strip().upper()
    if check_plate:
        wl, err = api_get(f"/watchlist/check/{check_plate}")
        if err:
            st.error(err)
        elif wl:
            if wl["watchlisted"]:
                st.error(f"⚠️ WATCHLISTED — reason: {wl['reason']}")
            else:
                st.success("Not on watchlist")
