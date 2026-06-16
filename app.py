import ast
from pathlib import Path

import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster


# ============================================================
# Config
# ============================================================

st.set_page_config(
    page_title="Qld AQMS Explorer",
    page_icon="🌏",
    layout="wide",
)

PARQUET_PATH = Path("qld_aqms.parquet")


# ============================================================
# Helpers
# ============================================================

@st.cache_data(show_spinner=False)
def load_parquet(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Parquet file not found: {path}")

    df = pd.read_parquet(path)

    # Normalize expected columns
    for col in ["csv_columns", "data_dictionary_columns"]:
        if col in df.columns:
            df[col] = df[col].apply(normalize_list_column)

    # Ensure numeric coords
    if "latitude" in df.columns:
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    if "longitude" in df.columns:
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    return df


def normalize_list_column(v):
    """
    Convert parquet-stored list/string/list-like text into a Python list of strings.
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []

    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]

    if isinstance(v, str):
        s = v.strip()

        # Try Python literal list first
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass

        # Fall back to comma-separated
        if "," in s:
            return [x.strip() for x in s.split(",") if x.strip()]

        return [s] if s else []

    return [str(v).strip()]


def get_all_csv_columns(df: pd.DataFrame) -> list[str]:
    cols = set()
    if "csv_columns" not in df.columns:
        return []

    for item in df["csv_columns"]:
        if isinstance(item, list):
            cols.update(item)
    return sorted(cols)


def match_columns(selected_cols, row_cols, match_mode="any"):
    """
    selected_cols: list[str]
    row_cols: list[str]
    """
    if not selected_cols:
        return True

    row_set = set(row_cols)
    sel_set = set(selected_cols)

    if match_mode == "all":
        return sel_set.issubset(row_set)
    return len(sel_set.intersection(row_set)) > 0


def filter_dataframe(
    df: pd.DataFrame,
    years: list[int],
    selected_columns: list[str],
    search_text: str,
    match_mode: str = "any",
) -> pd.DataFrame:
    out = df.copy()

    if "dataset_year" in out.columns and years:
        out = out[out["dataset_year"].isin(years)]

    if selected_columns:
        out = out[out["csv_columns"].apply(lambda x: match_columns(selected_columns, x, match_mode))]

    if search_text:
        q = search_text.strip().lower()

        def row_matches(row):
            vals = [
                str(row.get("station_name", "")),
                str(row.get("resource_title", "")),
                str(row.get("site_location_text", "")),
                str(row.get("period", "")),
            ]
            return any(q in v.lower() for v in vals)

        out = out[out.apply(row_matches, axis=1)]

    return out


def create_map(df: pd.DataFrame):
    """
    Build a folium map centered on Queensland-ish extent.
    """
    if df.empty:
        center = [-20.5, 146.5]
        zoom = 5
    else:
        center = [
            float(df["latitude"].dropna().mean()) if "latitude" in df.columns and df["latitude"].notna().any() else -20.5,
            float(df["longitude"].dropna().mean()) if "longitude" in df.columns and df["longitude"].notna().any() else 146.5,
        ]
        zoom = 5

    m = folium.Map(location=center, zoom_start=zoom, tiles="CartoDB positron")
    cluster = MarkerCluster().add_to(m)

    for _, row in df.iterrows():
        lat = row.get("latitude")
        lon = row.get("longitude")

        if pd.isna(lat) or pd.isna(lon):
            continue

        station = row.get("station_name") or row.get("resource_title") or "Unknown station"
        resource_title = row.get("resource_title", "")
        year = row.get("dataset_year", "")
        period = row.get("period", "")
        csv_url = row.get("csv_url", "")
        site_location = row.get("site_location_text", "")
        csv_cols = row.get("csv_columns", [])
        csv_cols_text = ", ".join(csv_cols[:12]) + (" ..." if len(csv_cols) > 12 else "")

        popup_html = f"""
        <div style="width: 320px;">
            <h4 style="margin: 0 0 8px 0;">{station}</h4>
            <div><b>Year:</b> {year}</div>
            <div><b>Resource:</b> {resource_title}</div>
            <div><b>Period:</b> {period}</div>
            <div><b>Site location:</b> {site_location}</div>
            <div><b>Coordinates:</b> {lat:.4f}, {lon:.4f}</div>
            <div style="margin-top: 8px;"><b>CSV columns:</b> {csv_cols_text}</div>
            <div style="margin-top: 12px;">
                <a href="{csv_url}" target="_blank"
                   style="
                        display:inline-block;
                        padding:8px 12px;
                        background:#2563eb;
                        color:white;
                        text-decoration:none;
                        border-radius:8px;
                        font-weight:600;
                   ">
                   Download CSV
                </a>
            </div>
        </div>
        """

        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=380),
            tooltip=f"{station} ({year})",
            icon=folium.Icon(color="red", icon="cloud"),
        ).add_to(cluster)

    return m


def make_download_link(url: str, label: str = "Open CSV") -> str:
    return f'<a href="{url}" target="_blank">{label}</a>'


# ============================================================
# App
# ============================================================

st.title("🌏 Queensland AQMS Explorer")
st.caption("Streamlit prototype: map + filterable station table + CSV URL downloads")

if not PARQUET_PATH.exists():
    st.error(
        f"Could not find `{PARQUET_PATH}`. "
        f"Please make sure your parquet file is saved in the same folder as this app."
    )
    st.stop()

df = load_parquet(PARQUET_PATH)

if df.empty:
    st.warning("The parquet file is empty.")
    st.stop()

# Basic column sanity
required_cols = ["dataset_year", "resource_title", "csv_url", "latitude", "longitude"]
missing = [c for c in required_cols if c not in df.columns]
if missing:
    st.error(f"Your parquet is missing required columns: {missing}")
    st.stop()

# Available filter values
all_years = sorted([int(y) for y in df["dataset_year"].dropna().unique()])
all_columns = get_all_csv_columns(df)

# Sidebar filters
with st.sidebar:
    st.header("Filters")

    selected_years = st.multiselect(
        "Year",
        options=all_years,
        default=all_years,
    )

    selected_csv_columns = st.multiselect(
        "CSV columns / pollutants",
        options=all_columns,
        default=[],
    )

    match_mode = st.radio(
        "Column match mode",
        options=["any", "all"],
        index=0,
        horizontal=True,
        help="Any = show stations containing at least one selected column. All = must contain all selected columns.",
    )

    search_text = st.text_input(
        "Search station / resource / site",
        value="",
        placeholder="e.g. Brisbane, PM2.5, Gladstone",
    )

    st.divider()

    st.write("### Selected columns")
    if selected_csv_columns:
        st.write(", ".join(selected_csv_columns))
    else:
        st.write("All columns")

    st.write("### Selected years")
    if selected_years:
        st.write(", ".join(map(str, selected_years)))
    else:
        st.write("None")

# Filter data
filtered_df = filter_dataframe(
    df=df,
    years=selected_years,
    selected_columns=selected_csv_columns,
    search_text=search_text,
    match_mode=match_mode,
)

# Optional: remove rows with no coordinates for map, but keep them in table
map_df = filtered_df[
    filtered_df["latitude"].notna() & filtered_df["longitude"].notna()
].copy()

# Top metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Matched rows", len(filtered_df))
c2.metric("Stations on map", len(map_df))
c3.metric("Years selected", len(selected_years))
c4.metric("Selected CSV columns", len(selected_csv_columns))

st.divider()

# Map
st.subheader("Station map")

if map_df.empty:
    st.info("No stations match the current filters.")
else:
    m = create_map(map_df)
    st_folium(m, width=None, height=600)

st.divider()

# Table
st.subheader("Filtered station table")

show_cols = [
    c for c in [
        "dataset_year",
        "station_name",
        "resource_title",
        "period",
        "site_location_text",
        "latitude",
        "longitude",
        "csv_url",
        "csv_columns",
    ]
    if c in filtered_df.columns
]

table_df = filtered_df[show_cols].copy()

if "csv_columns" in table_df.columns:
    table_df["csv_columns"] = table_df["csv_columns"].apply(
        lambda x: ", ".join(x) if isinstance(x, list) else ""
    )

if "csv_url" in table_df.columns:
    table_df["csv_url"] = table_df["csv_url"].apply(
        lambda u: make_download_link(u, "Open CSV") if pd.notna(u) and str(u).strip() else ""
    )

st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "csv_url": st.column_config.LinkColumn(
            "CSV download",
            display_text="Open CSV",
        ),
        "latitude": st.column_config.NumberColumn(format="%.5f"),
        "longitude": st.column_config.NumberColumn(format="%.5f"),
    },
)

st.divider()

# Row-wise download section
st.subheader("Download matching station CSVs")

if filtered_df.empty:
    st.write("No matching stations.")
else:
    st.write(
        "Use the buttons below to open the CSV for each filtered station."
    )

    # Show a manageable number of cards
    max_buttons = 50
    display_df = filtered_df.head(max_buttons)

    for _, row in display_df.iterrows():
        station = row.get("station_name") or row.get("resource_title") or "Unknown station"
        year = row.get("dataset_year", "")
        resource_title = row.get("resource_title", "")
        csv_url = row.get("csv_url", "")
        csv_cols = row.get("csv_columns", [])
        csv_cols_text = ", ".join(csv_cols[:10]) + (" ..." if len(csv_cols) > 10 else "")

        with st.container(border=True):
            left, right = st.columns([4, 1])
            with left:
                st.markdown(f"**{station}**  \nYear: `{year}`")
                st.caption(resource_title)
                st.write(f"**CSV columns:** {csv_cols_text}")
                if row.get("site_location_text"):
                    st.write(f"**Site location:** {row.get('site_location_text')}")
                if row.get("period"):
                    st.write(f"**Period:** {row.get('period')}")

            with right:
                if csv_url:
                    st.link_button("Open CSV", csv_url, use_container_width=True)

    if len(filtered_df) > max_buttons:
        st.info(f"Showing first {max_buttons} stations only for the download section.")

st.divider()

# Optional: export filtered metadata table
st.subheader("Export filtered metadata")
csv_export = filtered_df.drop(columns=["csv_columns"], errors="ignore").copy()
csv_bytes = csv_export.to_csv(index=False).encode("utf-8-sig")

st.download_button(
    label="Download filtered station metadata as CSV",
    data=csv_bytes,
    file_name="filtered_qld_aqms_stations_metadata.csv",
    mime="text/csv",
)