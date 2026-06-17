import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster
import pandas as pd

from utils import (
    load_data,
    filter_df,
    get_map_df,
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

POLLUTANTS = ['no2', 'o3', 'pm10', 'pm2_5', 'co', 'ws', 'wd']

years_available = sorted(
    set(df['Commissioned'].dropna().astype(int).tolist() +
        df['Decommissioned'].dropna().astype(int).tolist())
)

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

df_map = get_map_df(df_filtered)

# ============================================================
# Map
# ============================================================

st.subheader("Map")

m = folium.Map(location=[-33.5, 147.5], zoom_start=6)
cluster = MarkerCluster().add_to(m)

for _, row in df_map.iterrows():

    popup_html = f"""
    <b>{row['SiteName']}</b><br>
    Region: {row['Region']}<br>
    Site_Id: {row['Site_Id']}
    """

    folium.Marker(
        [row["Latitude"], row["Longitude"]],
        popup=popup_html,
        tooltip=row["SiteName"]
    ).add_to(cluster)

map_state = st_folium(m, height=600, use_container_width=True)

# ============================================================
# Detect click
# ============================================================

if "selected_site_id" not in st.session_state:
    st.session_state.selected_site_id = None

if map_state and map_state.get("last_clicked"):

    lat = map_state["last_clicked"]["lat"]
    lon = map_state["last_clicked"]["lng"]

    nearest = find_nearest_station(df_map, lat, lon)

    if nearest:
        st.session_state.selected_site_id = nearest

# ============================================================
# Download panel
# ============================================================

st.subheader("Download station data")

# default selection
default_idx = 0

if st.session_state.selected_site_id:
    match = df_filtered[df_filtered["Site_Id"] == st.session_state.selected_site_id]
    if not match.empty:
        default_idx = df_filtered.index.get_loc(match.index[0])

selected_station = st.selectbox(
    "Select station",
    df_filtered["SiteName"].tolist(),
    index=default_idx
)

row_sel = df_filtered[df_filtered["SiteName"] == selected_station].iloc[0]

site_id = row_sel["Site_Id"]

# ✅ dynamic param options
available_params = []

if row_sel["no2"]:
    available_params.append("NO2")
if row_sel["o3"]:
    available_params.append("OZONE")
if row_sel["pm10"]:
    available_params.append("PM10")
if row_sel["pm2_5"]:
    available_params.append("PM2.5")

param = st.selectbox("Parameter", available_params)

col1, col2 = st.columns(2)

with col1:
    start_date = st.date_input("Start date")

with col2:
    end_date = st.date_input("End date")

if st.button("Download data"):

    df_api = fetch_api_data(site_id, param, start_date, end_date)

    if df_api is None or df_api.empty:
        st.error("No data returned.")
    else:
        st.download_button(
            "Download CSV",
            df_api.to_csv(index=False).encode("utf-8"),
            file_name=f"{selected_station}_{param}.csv"
        )

# ============================================================
# Table
# ============================================================

st.subheader("Stations")

show_cols = [
    'SiteName',
    'Site_Id',
    'Region',
    'Latitude',
    'Longitude',
    'Commissioned',
    'Decommissioned',
    'Station purpose',
    'Site address',
    'Altitude (ahd)',
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