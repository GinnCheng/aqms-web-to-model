import pandas as pd
import re

# ------------------------------------------------------------
# 1. Collect all unique raw CSV column names
# ------------------------------------------------------------

def collect_unique_csv_columns(df):
    """
    Explode df['csv_columns'] and return unique raw column names.
    """
    if "csv_columns" not in df.columns:
        raise ValueError("df must contain a 'csv_columns' column.")

    unique_cols = (
        df["csv_columns"]
        .explode()
        .dropna()
        .astype(str)
        .str.strip()
    )

    unique_cols = unique_cols[unique_cols != ""].drop_duplicates().sort_values()
    return unique_cols.tolist()


# ------------------------------------------------------------
# 2. Normalize raw column names
# ------------------------------------------------------------

def normalize_text(s):
    """
    Lowercase, strip units, replace special chars with underscores.
    """
    s = str(s).strip().lower()

    # remove unit bracket content
    s = re.sub(r"\s*\(.*?\)", "", s)

    # normalize punctuation / spaces
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")

    return s


# ------------------------------------------------------------
# 3. Map raw names to clean names + abbreviations + category
# ------------------------------------------------------------

COLUMN_MAP = {
    # Timestamp / metadata
    "date": {"clean_name": "date", "abbr": "date", "category": "timestamp"},
    "time": {"clean_name": "time", "abbr": "time", "category": "timestamp"},

    # Meteorology
    "wind_direction": {"clean_name": "wind_direction", "abbr": "wd", "category": "meteorology"},
    "wind_speed": {"clean_name": "wind_speed", "abbr": "ws", "category": "meteorology"},
    "wind_sigma_theta": {"clean_name": "wind_sigma_theta", "abbr": "sigma_theta", "category": "meteorology"},
    "wind_speed_std_dev": {"clean_name": "wind_speed_std_dev", "abbr": "ws_sd", "category": "meteorology"},
    "air_temperature": {"clean_name": "air_temperature", "abbr": "temp", "category": "meteorology"},
    "relative_humidity": {"clean_name": "relative_humidity", "abbr": "rh", "category": "meteorology"},
    "rainfall": {"clean_name": "rainfall", "abbr": "rain", "category": "meteorology"},
    "barometric_pressure": {"clean_name": "barometric_pressure", "abbr": "bp", "category": "meteorology"},
    "solar_radiation": {"clean_name": "solar_radiation", "abbr": "sr", "category": "meteorology"},

    # Gas pollutants
    "ozone": {"clean_name": "ozone", "abbr": "o3", "category": "gas"},
    "nitrogen_oxide": {"clean_name": "nitrogen_oxide", "abbr": "no", "category": "gas"},
    "nitrogen_dioxide": {"clean_name": "nitrogen_dioxide", "abbr": "no2", "category": "gas"},
    "nitrogen_oxides": {"clean_name": "nitrogen_oxides", "abbr": "nox", "category": "gas"},
    "sulfur_dioxide": {"clean_name": "sulfur_dioxide", "abbr": "so2", "category": "gas"},
    "carbon_monoxide": {"clean_name": "carbon_monoxide", "abbr": "co", "category": "gas"},
    "benzene": {"clean_name": "benzene", "abbr": "benzene", "category": "gas"},
    "formaldehyde": {"clean_name": "formaldehyde", "abbr": "hcho", "category": "gas"},
    "toluene": {"clean_name": "toluene", "abbr": "toluene", "category": "gas"},
    "xylenes": {"clean_name": "xylenes", "abbr": "xylenes", "category": "gas"},

    # Particles / aerosols
    "pm10": {"clean_name": "pm10", "abbr": "pm10", "category": "particle"},
    "pm25": {"clean_name": "pm25", "abbr": "pm25", "category": "particle"},
    "tsp": {"clean_name": "tsp", "abbr": "tsp", "category": "particle"},
    "visibility_reducing_particles": {"clean_name": "visibility_reducing_particles", "abbr": "vrp", "category": "particle"},
}


def raw_to_base_key(raw_name):
    """
    Convert raw CSV header to a base key used for mapping.
    """
    s = normalize_text(raw_name)

    # special handling for common forms
    replacements = {
        "wind_direction_degtn": "wind_direction",
        "wind_speed_m_s": "wind_speed",
        "wind_sigma_theta_deg": "wind_sigma_theta",
        "wind_speed_std_dev_m_s": "wind_speed_std_dev",
        "air_temperature_deg_c": "air_temperature",
        "relative_humidity": "relative_humidity",
        "rainfall_mm": "rainfall",
        "barometric_pressure_hpa": "barometric_pressure",
        "solar_radiation_w_m_2": "solar_radiation",
        "nitrogen_oxide_ppm": "nitrogen_oxide",
        "nitrogen_dioxide_ppm": "nitrogen_dioxide",
        "nitrogen_oxides_ppm": "nitrogen_oxides",
        "sulfur_dioxide_ppm": "sulfur_dioxide",
        "carbon_monoxide_ppm": "carbon_monoxide",
        "ozone_ppm": "ozone",
        "pm10_ug_m_3": "pm10",
        "pm2_5_ug_m_3": "pm25",
        "tsp_ug_m_3": "tsp",
        "visibility_reducing_particles_mm_1": "visibility_reducing_particles",
    }

    return replacements.get(s, s)


def map_column(raw_name):
    """
    Return clean mapping info for one raw CSV header.
    """
    base_key = raw_to_base_key(raw_name)
    mapping = COLUMN_MAP.get(base_key)

    if mapping:
        return {
            "raw_column": raw_name,
            "base_key": base_key,
            "clean_name": mapping["clean_name"],
            "abbr": mapping["abbr"],
            "category": mapping["category"],
        }

    # fallback: make a generic cleaned name
    return {
        "raw_column": raw_name,
        "base_key": base_key,
        "clean_name": base_key,
        "abbr": base_key,
        "category": "other",
    }


# ------------------------------------------------------------
# 4. Create a unique schema mapping dataframe
# ------------------------------------------------------------

def build_column_dictionary(df):
    """
    Build a dataframe of all unique raw CSV columns and their cleaned names.
    """
    unique_cols = collect_unique_csv_columns(df)
    mapping_rows = [map_column(col) for col in unique_cols]
    mapping_df = pd.DataFrame(mapping_rows)

    # optional: sort by category then clean name
    mapping_df = mapping_df.sort_values(["category", "clean_name", "raw_column"]).reset_index(drop=True)
    return mapping_df