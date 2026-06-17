import pandas as pd
import streamlit as st
import folium
import requests
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster

# ============================================================
# Config
# ============================================================

st.set_page_config(page_title="NSW AQMS Explorer", layout="wide")

PARQUET_PATH = "nsw_aqms_full.parquet"
API_URL = "https://data.airquality.nsw.gov.au/api/Data/get_Observations"


# ============================================================
# Load
# ============================================================

@st.cache_data
def load_data(path):
    df = pd.read_parquet(path)

    # clean column names
    df.columns = (
        df.columns
        .str.strip()
        .str.replace('\n', ' ')
        .str.replace('\xa0', '')
    )

    # coordinates
    df["Latitude"] = pd.to_numeric(df["Latitude_api"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude_api"], errors="coerce")

    # time fields
    df["Commissioned"] = pd.to_numeric(df["Commissioned"], errors="coerce")
    df["Decommissioned"] = pd.to_numeric(df["Decommissioned"], errors="coerce")

    df["is_active"] = df["Decommissioned"].isna()

    return df


df = load_data(PARQUET_PATH)


# ============================================================
# Helpers
# ============================================================

def is_active_in_years(row, years):
    if not years:
        return True

    start = row["Commissioned"]
    end = row["Decommissioned"]

    for y in years:
        if pd.notna(start) and start <= y:
            if pd.isna(end) or end >= y:
                return True
    return False


def fetch_api_data(site_id, param, start, end):
    payload = {
        "Parameters": [param],
        "Sites": [int(site_id)],
        "StartDate": str(start),
        "EndDate": str(end),
        "Categories": ["Averages"],
        "SubCategories": ["Hourly"],
        "Frequency": ["Hourly average"]
    }

    r = requests.post(API_URL, json=payload)

    if r.status_code != 200:
        return None

    return pd.json_normalize(r.json())


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

df_filtered = df.copy()

# year filter
if selected_years:
    df_filtered = df_filtered[
        df_filtered.apply(lambda r: is_active_in_years(r, selected_years), axis=1)
    ]

# pollutant filter
if selected_pollutants:
    if match_mode == "all":
        df_filtered = df_filtered[df_filtered[selected_pollutants].all(axis=1)]
    else:
        df_filtered = df_filtered[df_filtered[selected_pollutants].any(axis=1)]

# search
if search:
    df_filtered = df_filtered[df_filtered["SiteName"].str.contains(search, case=False, na=False)]

# clean coords
df_filtered = df_filtered[
    df_filtered["Latitude"].notna() &
    df_filtered["Longitude"].notna()
]

# ✅ fix marker duplication
df_map = df_filtered.drop_duplicates(subset=["Site_Id"])


# ============================================================
# Map
# ============================================================

st.subheader("Map")

m = folium.Map(location=[-33.5, 147.5], zoom_start=6)
cluster = MarkerCluster().add_to(m)

for _, row in df_map.iterrows():

    # query param link
    download_url = f"?site_id={row['Site_Id']}&site={row['SiteName']}"

    params = ", ".join(row["Parameters"]) if isinstance(row["Parameters"], list) else ""

    popup_html = f"""
    <b>{row['SiteName']}</b><br>
    Region: {row['Region']}<br>
    Site_Id: {row['Site_Id']}<br>
    Parameters: {params}<br><br>

    <a href="{download_url}">
        <button style="
            background-color:#2563eb;
            color:white;
            border:none;
            padding:6px 10px;
            border-radius:6px;
            cursor:pointer;
        ">
            Download Data
        </button>
    </a>
    """

    folium.Marker(
        [row["Latitude"], row["Longitude"]],
        popup=folium.Popup(popup_html, max_width=300),
        tooltip=row["SiteName"]
    ).add_to(cluster)

st_folium(m, height=600)


# ============================================================
# Handle map click download
# ============================================================

params_query = st.query_params

if "site_id" in params_query:
    st.subheader("Download station data (from map click)")

    site_id = int(params_query["site_id"])
    site_name = params_query.get("site", "Unknown")

    st.write(f"Selected station: **{site_name}** (ID: {site_id})")

    param = st.selectbox(
        "Parameter",
        ["NO2", "OZONE", "PM10", "PM2.5"],
        key="map_param"
    )

    start_date = st.date_input("Start date", key="map_start")
    end_date = st.date_input("End date", key="map_end")

    if st.button("Download data", key="map_download"):

        df_api = fetch_api_data(site_id, param, start_date, end_date)

        if df_api is None or df_api.empty:
            st.error("No data returned.")
        else:
            csv = df_api.to_csv(index=False).encode("utf-8")

            st.download_button(
                "Download CSV",
                csv,
                file_name=f"{site_name}_{param}.csv"
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

# safe filtering
show_cols = [c for c in show_cols if c in df_filtered.columns]

st.dataframe(
    df_filtered[show_cols],
    use_container_width=True,
    column_config={
        "Web link to station meta data page":
            st.column_config.LinkColumn("Station Page")
    }
)