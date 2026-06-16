import re
import time
from io import BytesIO
from urllib.parse import urljoin, quote

import pandas as pd
import requests
from bs4 import BeautifulSoup

# ============================================================
# Configuration
# ============================================================

BASE = "https://www.data.qld.gov.au"
DEFAULT_QUERY = "air quality monitoring"
DEFAULT_YEARS = [2014, 2015, 2016, 2020, 2021, 2022, 2023, 2024]
DEFAULT_MAX_SEARCH_PAGES = 10
DEFAULT_SLEEP_SECONDS = 0.4

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; QLD-AQMS-scraper/1.0; +https://www.data.qld.gov.au)"
})

# ============================================================
# Utilities
# ============================================================

def clean_text(s):
    if s is None:
        return None
    return re.sub(r"\s+", " ", str(s)).strip()

def unique_keep_order(items):
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out

def fetch_url(url, timeout=30, sleep=DEFAULT_SLEEP_SECONDS):
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    time.sleep(sleep)
    return r.text

def fetch_soup(url, timeout=30, sleep=DEFAULT_SLEEP_SECONDS):
    html = fetch_url(url, timeout=timeout, sleep=sleep)
    return BeautifulSoup(html, "html.parser"), html

def safe_float(x):
    try:
        return float(x)
    except Exception:
        return None

# ============================================================
# 1) Find AQMS dataset pages from search results
# ============================================================

def find_dataset_pages(query=DEFAULT_QUERY, years=None, max_pages=DEFAULT_MAX_SEARCH_PAGES):
    """
    Search the QLD data portal and collect dataset page URLs whose titles match
    'Air Quality Monitoring - YYYY' (and optionally the grouped-by-pollutant variant).
    """
    years = set(years) if years else None
    found = []

    for page in range(max_pages):
        search_url = f"{BASE}/dataset?q={quote(query)}&page={page+1}"
        soup, _ = fetch_soup(search_url)

        links = []
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            title = clean_text(a.get_text(" ", strip=True))
            if "/dataset/" in href and title:
                links.append((urljoin(BASE, href), title))

        for url, title in unique_keep_order(links):
            m = re.search(r"Air Quality Monitoring - (\d{4})", title, re.I)
            if not m:
                continue

            year = int(m.group(1))
            if years is not None and year not in years:
                continue

            found.append({
                "dataset_year": year,
                "dataset_title": title,
                "dataset_page_url": url
            })

    df = pd.DataFrame(found).drop_duplicates(subset=["dataset_page_url"]).reset_index(drop=True)
    return df

# ============================================================
# 2) Extract resource page URLs from a dataset page
# ============================================================

def extract_resource_page_urls(dataset_page_url):
    """
    Return resource detail page URLs from a dataset page.
    We intentionally avoid direct /download/ links here.
    """
    soup, _ = fetch_soup(dataset_page_url)

    resource_urls = []
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if "/resource/" in href and "/download/" not in href:
            resource_urls.append(urljoin(BASE, href))

    return unique_keep_order(resource_urls)

# ============================================================
# 3) Read actual CSV headers from the file
# ============================================================

def get_csv_headers(csv_url):
    """
    Read only the header row from the CSV and return the actual column names.
    """
    if not csv_url:
        return None

    try:
        r = session.get(csv_url, timeout=60)
        r.raise_for_status()

        # Try common encodings robustly
        content = r.content
        try:
            df_header = pd.read_csv(BytesIO(content), nrows=0)
        except Exception:
            df_header = pd.read_csv(BytesIO(content), nrows=0, encoding="latin1")

        return list(df_header.columns)

    except Exception:
        return None

# ============================================================
# 4) Parse a resource page for metadata
# ============================================================

def parse_data_dictionary_columns(full_text):
    """
    Extract the portal's documented data dictionary field names.
    Example text:
      Data Dictionary 1. Date timestamp 2. Time text 3. Wind Direction (degTN) text ...
    """
    m = re.search(
        r"Data Dictionary(.*?)(?:Additional Information|Data last updated|Metadata last updated|$)",
        full_text,
        re.S | re.I
    )
    if not m:
        return []

    section = m.group(1)

    fields = re.findall(
        r"\b\d+\.\s*(.+?)(?=\s+(?:text|numeric|number)\b)",
        section,
        flags=re.I
    )

    fields = [clean_text(f) for f in fields]
    return unique_keep_order([f for f in fields if f])

def extract_first_match(pattern, text, flags=re.I, group=1):
    m = re.search(pattern, text, flags)
    if not m:
        return None
    return clean_text(m.group(group))

def parse_resource_page(resource_page_url):
    """
    Parse a resource page and return a metadata dictionary.
    """
    soup, html = fetch_soup(resource_page_url)
    text = clean_text(soup.get_text(" ", strip=True))

    # Title
    title = None
    for tag in ["h1", "h2", "title"]:
        el = soup.find(tag)
        if el:
            title = clean_text(el.get_text(" ", strip=True))
            if title:
                break

    # Find a likely CSV URL
    csv_url = None
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if ".csv" in href.lower() or "/download/" in href.lower():
            csv_url = urljoin(BASE, href)
            if href.lower().endswith(".csv") or ".csv?" in href.lower():
                break

    # Period of operation / reporting
    period = extract_first_match(
        r"Period of (?:operation|reporting):\s*(.*?)(?=(?:Site location:|Measurement units:|Measurement technique:|Data Dictionary|Additional Information|$))",
        text
    )

    # Site location text
    site_location_text = extract_first_match(
        r"Site location:\s*(.*?)(?=(?:AS/NZS|Height above ground level:|Temperature:|Relative humidity:|Rainfall:|Barometric pressure:|Sulfur dioxide:|Sulphur dioxide:|PM10/PM2\.5:|Measurement technique:|Data Dictionary|Additional Information|$))",
        text
    )

    # Latitude / Longitude
    latitude = extract_first_match(r"Latitude:\s*([-\d.]+)", text)
    longitude = extract_first_match(r"Longitude:\s*([-\d.]+)", text)

    latitude = safe_float(latitude)
    longitude = safe_float(longitude)

    # Site classification
    site_classification = extract_first_match(
        r"AS/NZS 3580\.1\.1[^:]*site classification:\s*(.*?)(?=(?:AS/NZS|Height above ground level:|Temperature:|Relative humidity:|Rainfall:|Barometric pressure:|Measurement technique:|Data Dictionary|Additional Information|$))",
        text
    )

    if not site_classification:
        site_classification = extract_first_match(
            r"site classification:\s*(.*?)(?=(?:AS/NZS|Height above ground level:|Temperature:|Relative humidity:|Rainfall:|Barometric pressure:|Measurement technique:|Data Dictionary|Additional Information|$))",
            text
        )

    # Compliance notes
    compliance_pollutants = extract_first_match(
        r"AS/NZS 3580\.1\.1[^:]*compliance \(pollutants\):\s*(.*?)(?=(?:AS/NZS 3580\.14 compliance \(meteorology\):|Height above ground level:|Temperature:|Relative humidity:|Rainfall:|Barometric pressure:|Measurement technique:|Data Dictionary|Additional Information|$))",
        text
    )

    compliance_meteorology = extract_first_match(
        r"AS/NZS 3580\.14 compliance \(meteorology\)\s*:\s*(.*?)(?=(?:Height above ground level:|Temperature:|Relative humidity:|Rainfall:|Barometric pressure:|Measurement technique:|Data Dictionary|Additional Information|$))",
        text
    )

    # Height notes (can appear multiple times)
    height_notes = unique_keep_order(
        re.findall(r"Height above ground level:\s*([\d.]+\s*metres?|[\d.]+\s*m)", text, re.I)
    )
    height_notes_text = "; ".join(height_notes) if height_notes else None

    # Measurement / sensor notes (keep the raw block where possible)
    measurement_notes = None
    m = re.search(
        r"(?:Measurement technique|Temperature:|Relative humidity:|Rainfall:|Barometric pressure:|Sulfur dioxide:|Sulphur dioxide:|PM10/PM2\.5:)(.*?)(?=(?:Data Dictionary|Additional Information|$))",
        text,
        re.I
    )
    if m:
        measurement_notes = clean_text(m.group(0))

    # Portal-documented data dictionary fields
    data_dictionary_columns = parse_data_dictionary_columns(text)

    return {
        "resource_page_url": resource_page_url,
        "resource_title": title,
        "csv_url": csv_url,
        "period": period,
        "site_location_text": site_location_text,
        "latitude": latitude,
        "longitude": longitude,
        "site_classification": site_classification,
        "compliance_pollutants": compliance_pollutants,
        "compliance_meteorology": compliance_meteorology,
        "height_notes": height_notes_text,
        "measurement_notes": measurement_notes,
        "data_dictionary_columns": data_dictionary_columns,
    }

# ============================================================
# 5) Build the full dataframe
# ============================================================

def build_aqms_dataframe(
    years=DEFAULT_YEARS,
    query=DEFAULT_QUERY,
    max_pages=DEFAULT_MAX_SEARCH_PAGES,
    sleep_between_resources=DEFAULT_SLEEP_SECONDS
):
    """
    Build one row per resource page, with actual CSV headers in csv_columns.
    """
    dataset_df = find_dataset_pages(query=query, years=years, max_pages=max_pages)

    all_rows = []

    for _, drow in dataset_df.iterrows():
        dataset_year = drow["dataset_year"]
        dataset_title = drow["dataset_title"]
        dataset_page_url = drow["dataset_page_url"]

        try:
            resource_page_urls = extract_resource_page_urls(dataset_page_url)
        except Exception as e:
            all_rows.append({
                "dataset_year": dataset_year,
                "dataset_title": dataset_title,
                "dataset_page_url": dataset_page_url,
                "error": f"Failed to extract resource URLs: {e}"
            })
            continue

        for resource_page_url in resource_page_urls:
            row = {
                "dataset_year": dataset_year,
                "dataset_title": dataset_title,
                "dataset_page_url": dataset_page_url,
                "resource_page_url": resource_page_url,
            }

            try:
                meta = parse_resource_page(resource_page_url)
                row.update(meta)

                # Read the actual CSV headers from the live CSV
                row["csv_columns"] = get_csv_headers(meta.get("csv_url"))

                # Optional helper string columns for easy viewing/export
                row["csv_columns_str"] = (
                    ", ".join(row["csv_columns"]) if isinstance(row.get("csv_columns"), list) else None
                )
                row["data_dictionary_columns_str"] = (
                    ", ".join(row["data_dictionary_columns"]) if isinstance(row.get("data_dictionary_columns"), list) else None
                )

            except Exception as e:
                row["error"] = str(e)

            all_rows.append(row)
            time.sleep(sleep_between_resources)

    df = pd.DataFrame(all_rows)

    # Make sure list columns are preserved nicely in CSV/Excel exports
    for col in ["csv_columns", "data_dictionary_columns"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: x if isinstance(x, list) else x)

    return df

# ============================================================
# 6) Optional helper: explode csv columns into a long table
# ============================================================

def explode_csv_columns(df):
    """
    Convert one row per resource into one row per CSV column.
    Useful if you want to compare schemas across years/resources.
    """
    if "csv_columns" not in df.columns:
        raise ValueError("Input dataframe must contain a 'csv_columns' column.")

    out = df.copy()
    out = out.explode("csv_columns")
    out = out.rename(columns={"csv_columns": "csv_column"})
    return out

# 7) Main execution
# ============================================================

if __name__ == "__main__":
    years_to_scrape = [2014, 2015, 2016, 2020, 2021, 2022, 2023, 2024]

    df = build_aqms_dataframe(
        years=years_to_scrape,
        query="air quality monitoring",
        max_pages=10,
        sleep_between_resources=0.4
    )

    # Save outputs
    df.to_csv("qld_aqms_resources.csv", index=False, encoding="utf-8-sig")
    df.to_excel("qld_aqms_resources.xlsx", index=False)

    # Optional: normalized long form of actual csv column names
    df_long = explode_csv_columns(df) if "csv_columns" in df.columns else pd.DataFrame()
    if not df_long.empty:
        df_long.to_csv("qld_aqms_resources_long.csv", index=False, encoding="utf-8-sig")
        df_long.to_excel("qld_aqms_resources_long.xlsx", index=False)

    print("Done.")
    print(f"Rows scraped: {len(df)}")
    print("\nPreview:")
    print(df.head(10).to_string(index=False))

    if not df.empty and "csv_columns_str" in df.columns:
        print("\nExample csv_columns_str:")
        print(df.loc[df["csv_columns_str"].notna(), "csv_columns_str"].head(5).to_string(index=False))