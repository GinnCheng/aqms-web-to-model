# Build raw -> normalized code lookup from mapping_df
# Prefer 'abbr' if available, otherwise 'clean_name'
from qld_aqms_df_clean import build_column_dictionary


TARGET_CODES = [
        "co",
        "no2",
        "pm2_5",
        "pm10",
        "tsp",
        "o3",
        "so2",
        "wd",
        "ws",
    ]

def qld_aqms_build_mapping_lookup(df):
    mapping_df = build_column_dictionary(df)

    mapping_lookup = (
        mapping_df
        .assign(
            normalized_code=lambda x: x["abbr"].fillna(x["clean_name"])
        )
        .set_index("raw_column")["normalized_code"]
        .to_dict()
    )


    td = add_pollutant_flags(df, mapping_lookup, TARGET_CODES)
    return td


def normalize_csv_columns(raw_cols, mapping_lookup):
    """
    Convert raw CSV headers to normalized codes using mapping_lookup.
    """
    if not isinstance(raw_cols, list):
        return []

    normalized = []
    for c in raw_cols:
        c = str(c).strip()
        normalized.append(mapping_lookup.get(c, c))  # fallback to raw if not mapped

    return list(dict.fromkeys(normalized))


def add_pollutant_flags(df, mapping_lookup, target_codes):
    """
    Add boolean columns to df indicating whether each target code exists
    in the station's CSV columns.
    """
    out = df.copy()

    # normalized list per row
    out["csv_columns_clean"] = out["csv_columns"].apply(
        lambda cols: normalize_csv_columns(cols, mapping_lookup)
    )

    # boolean flags
    for code in target_codes:
        out[code] = out["csv_columns_clean"].apply(
            lambda cols: code in cols if isinstance(cols, list) else False
        )

    return out