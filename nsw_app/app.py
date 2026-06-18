import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster
import pandas as pd

from utils import (
    load_data,
    filter_df,
    find_nearest_station,
    fetch_api_data
)

# ============================================================
# Config
# ============================================================

st.set_page_config(page_title="NSW AQMS Explorer", layout="wide")

PARQUET_PATH = "nsw_aqms_full.parquet"

# ============================================================
# Load
# ============================================================

@st.cache_data
def load():
    return load_data(PARQUET_PATH)

df = load()

# ============================================================
# Sidebar
# ============================================================

# ✅ FIXED comma
POLLUTANTS = ['ws','wd','no2','pm10_day','pm2_5_day','co','o3','pm10','pm2_5']

years_available = list(range(2020, pd.Timestamp.now().year + 1))
years_available.reverse()

with st.sidebar:
    st.header("Filters")

    selected_years = st.multiselect("Year", years_available)
    selected_pollutants = st.multiselect("Pollutants", POLLUTANTS)
    match_mode = st.radio("Match mode", ["any", "all"], horizontal=True)
    search = st.text_input("Search station")

# ============================================================
# Filtering
# ============================================================

df_filtered = filter_df(
    df,
    selected_years,
    selected_pollutants,
    match_mode,
    search
)

if df_filtered.empty:
    st.warning("No stations match the current filters. Please adjust your filters.")

    # ✅ still show empty table for clarity
    st.subheader("Stations")
    st.dataframe(df_filtered)

    st.stop()   # 🔥 CRITICAL: stop rest of app

# ✅ FIXED map dataframe
df_map = (
    df_filtered
    .drop_duplicates(subset=["Site_Id"])
    .dropna(subset=["Latitude", "Longitude"])
    .reset_index(drop=True)
)

# ============================================================
# Map
# ============================================================

st.subheader("Map")

if not df_map.empty:
    center = [df_map["Latitude"].mean(), df_map["Longitude"].mean()]
else:
    center = [-33.5, 147.5]

m = folium.Map(location=center, zoom_start=6)
cluster = MarkerCluster().add_to(m)

# ✅ CLEAN popup (no JS)
for _, row in df_map.iterrows():

    folium.Marker(
        location=[row["Latitude"], row["Longitude"]],
        tooltip=row["SiteName"],
        popup=f"{row['SiteName']} (ID {int(row['Site_Id'])})"
    ).add_to(cluster)

map_state = st_folium(m, height=500, use_container_width=True)

# ============================================================
# Detect click (WORKING)
# ============================================================
if "selected_site_id" not in st.session_state:
    st.session_state.selected_site_id = None

if map_state and map_state.get("last_object_clicked_tooltip"):

    tooltip = map_state["last_object_clicked_tooltip"]

    # tooltip format: "SiteName"
    match = df_map[df_map["SiteName"] == tooltip]

    if not match.empty:
        site_id = int(match.iloc[0]["Site_Id"])

        if st.session_state.selected_site_id != site_id:
            st.session_state.selected_site_id = site_id
            st.rerun()

# ============================================================
# Download panel
# ============================================================

st.subheader("Download station data")

df_ui = df_filtered.reset_index(drop=True)

# ✅ mapping
station_dict = {
    int(r["Site_Id"]): r["SiteName"]
    for _, r in df_ui.iterrows()
}

site_ids = list(station_dict.keys())

# ✅ initialise safely
if "selected_site_id" not in st.session_state:
    st.session_state.selected_site_id = site_ids[0] if site_ids else None

# ✅ FIX: if selected station not in filtered → reset
if st.session_state.selected_site_id not in site_ids:
    st.session_state.selected_site_id = site_ids[0] if site_ids else None

# ✅ controlled selectbox
selected_site_id = st.selectbox(
    "Select station",
    site_ids,
    format_func=lambda x: f"{station_dict[x]} (ID {x})",
    key="selected_site_id"
)

# ✅ SAFE row selection
match = df_ui[df_ui["Site_Id"] == selected_site_id]

if match.empty:
    st.warning("Selected station not in current filter. Showing first available.")
    row_sel = df_ui.iloc[0]
    selected_site_id = row_sel["Site_Id"]
    st.session_state.selected_site_id = selected_site_id
else:
    row_sel = match.iloc[0]

# ✅ FULL params
param_map = {
    "ws": "Wind Speed",
    "wd": "Wind Direction",
    "no2": "NO2",
    "o3": "OZONE",
    "pm10": "PM10",
    "pm2_5": "PM2.5",
    "pm10_day": "PM10d",
    "pm2_5_day": "PM2.5d",
    "co": "CO"
}

available_params = [
    api for col, api in param_map.items()
    if col in row_sel and bool(row_sel[col])
]

param = st.selectbox("Parameter", available_params)

col1, col2 = st.columns(2)

with col1:
    start_date = st.date_input("Start date")

with col2:
    end_date = st.date_input("End date")

if st.button("Download data"):

    df_api = fetch_api_data(selected_site_id, param, start_date, end_date)

    if df_api is None or df_api.empty:
        st.error("No data returned.")
    else:
        st.download_button(
            "Download CSV",
            df_api.to_csv(index=False).encode("utf-8"),
            file_name=f"{station_dict[selected_site_id]}_{param}.csv"
        )

# ============================================================
# Table
# ============================================================

st.subheader("Stations")

show_cols = [
    'SiteName','Site_Id','Region','Latitude','Longitude',
    'Commissioned','Decommissioned',
    'Station purpose','Site address','Altitude (ahd)',
    'Web link to station meta data page'
]

show_cols = [c for c in show_cols if c in df_filtered.columns]

st.dataframe(
    df_filtered[show_cols],
    use_container_width=True,
    column_config={
        "Web link to station meta data page":
            st.column_config.LinkColumn("Station Page")
    }
)