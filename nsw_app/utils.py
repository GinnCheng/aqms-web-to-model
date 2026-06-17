import pandas as pd
import requests
import numpy as np

API_URL = "https://data.airquality.nsw.gov.au/api/Data/get_Observations"


# ============================================================
# Load + clean
# ============================================================

def load_data(path):
    df = pd.read_parquet(path)

    df.columns = (
        df.columns
        .str.strip()
        .str.replace('\n', ' ')
        .str.replace('\xa0', '')
    )

    df["Latitude"] = pd.to_numeric(df["Latitude_api"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude_api"], errors="coerce")

    df["Commissioned"] = pd.to_numeric(df["Commissioned"], errors="coerce")
    df["Decommissioned"] = pd.to_numeric(df["Decommissioned"], errors="coerce")

    df["is_active"] = df["Decommissioned"].isna()

    return df


# ============================================================
# Filtering helpers
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


def filter_df(df, years, pollutants, match_mode, search):

    df_filtered = df.copy()

    # year filter
    if years:
        df_filtered = df_filtered[
            df_filtered.apply(lambda r: is_active_in_years(r, years), axis=1)
        ]

    # pollutant filter
    if pollutants:
        if match_mode == "all":
            df_filtered = df_filtered[df_filtered[pollutants].all(axis=1)]
        else:
            df_filtered = df_filtered[df_filtered[pollutants].any(axis=1)]

    # search
    if search:
        df_filtered = df_filtered[
            df_filtered["SiteName"].str.contains(search, case=False, na=False)
        ]

    # clean coords
    df_filtered = df_filtered[
        df_filtered["Latitude"].notna() &
        df_filtered["Longitude"].notna()
    ]

    return df_filtered


# ============================================================
# Map helpers
# ============================================================

def get_map_df(df):
    return df.drop_duplicates(subset=["Site_Id"])


def find_nearest_station(df_map, lat, lon, threshold=0.05):
    distances = np.sqrt(
        (df_map["Latitude"] - lat)**2 +
        (df_map["Longitude"] - lon)**2
    )

    idx = distances.idxmin()

    if distances.loc[idx] < threshold:
        return df_map.loc[idx, "Site_Id"]

    return None


# ============================================================
# API
# ============================================================

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
