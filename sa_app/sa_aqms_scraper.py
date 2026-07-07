import requests
import pandas as pd

class sa_aqms_manager:
    def __init__(self):
        self.base = "https://data.sa.gov.au/data/api/3/action/package_search"
        self.params = {
    "fq": "organization:environment-protection-authority-epa",
    "rows": 1000
}

    @staticmethod
    def is_aqms(ds):
        title = ds.get("title", "").lower()
        return "air quality" in title or "monitoring station" in title

    def get_aqms_data(self):

        data = requests.get(self.base, params=self.params).json()["result"]["results"]

        aqms = [ds for ds in data if self.is_aqms(ds)]

        records = []

        for ds in aqms:
            title = ds["title"]
            region = ds.get("spatial_coverage")
            granularity = ds.get("data_granularity")

            # crude pollutant extraction
            name_lower = ds["name"].lower()
            if "particle" in name_lower:
                pollutant = "PM"
            elif "gas" in name_lower:
                pollutant = "Gases"
            else:
                pollutant = "Unknown"

            years = []
            downloads = []

            for r in ds["resources"]:
                name = r.get("name", "")

                # extract year(s)
                import re

                year_match = re.findall(r"\d{4}", name)
                years.extend(year_match)

                downloads.append({
                    "name": name,
                    "url": r.get("url")
                })

            records.append({
                "station_title": title,
                "dataset_name": ds["name"],
                "region": region,
                "pollutant": pollutant,
                "data_granularity": granularity,
                "years_available": sorted(set(years)),
                "n_resources": len(ds["resources"]),
                "downloads": downloads
            })

        df = pd.DataFrame(records)

        return df