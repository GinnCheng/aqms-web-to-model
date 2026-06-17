import os, sys, requests, logging, urllib, json
import datetime as dt
import pandas as pd


def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]


class aqms_api_class():
    def __init__(self):
        self.logger = logging.getLogger(__file__)
        self.url_api = "https://data.airquality.nsw.gov.au"
        self.headers = {'content-type': 'application/json', 'accept': 'application/json'}
        self.get_site_url = '/api/Data/get_SiteDetails'
        self.get_parameters = '/api/Data/get_ParameterDetails'
        self.get_observations = '/api/Data/get_Observations'

    def get_site_details(self):
        query = urllib.parse.urljoin(self.url_api, self.get_site_url)
        response = requests.get(url=query, data='')
        response.raise_for_status()
        return response

    def get_parameter_details(self):
        query = urllib.parse.urljoin(self.url_api, self.get_parameters)
        response = requests.get(url=query, data='')
        response.raise_for_status()
        return response

    def get_Obs(self, ObsRequest):
        query = urllib.parse.urljoin(self.url_api, self.get_observations)
        response = requests.post(
            url=query,
            json=ObsRequest,
            headers=self.headers
        )
        response.raise_for_status()
        return response

    def get_full_station_metadata(self,
                                  start_date='2024-01-01',
                                  end_date='2024-01-02'):

        # --- 1. Metadata ---
        sites = self.get_site_details().json()
        params = self.get_parameter_details().json()

        df_sites = pd.DataFrame(sites)
        df_params = pd.DataFrame(params)

        df_sites.columns = df_sites.columns.str.strip()
        df_params.columns = df_params.columns.str.strip()

        site_ids = df_sites['Site_Id'].tolist()
        param_codes = df_params['ParameterCode'].tolist()

        # --- 2. Chunked observation queries ---
        site_chunks = list(chunk_list(site_ids, 10))
        param_chunks = list(chunk_list(param_codes, 10))

        all_data = []

        for sc in site_chunks:
            for pc in param_chunks:
                print(f'site {sc}, params {pc}')
                req = {
                    'Parameters': pc,
                    'Sites': sc,
                    'StartDate': start_date,
                    'EndDate': end_date,
                    'Categories': ['Averages'],
                    'SubCategories': ['Hourly'],
                    'Frequency': ['Hourly average']
                }

                try:
                    data = self.get_Obs(req).json()
                    if data:                         # ✅ avoid empty extends
                        all_data.extend(data)
                except requests.HTTPError as e:
                    self.logger.warning(
                        f"Failed chunk Sites={sc} Params={pc}: {e}"
                    )

        # ✅ handle complete failure safely
        if len(all_data) == 0:
            self.logger.warning("No observation data collected.")
            df_sites['Parameters'] = [[] for _ in range(len(df_sites))]
            return df_sites

        df_obs = pd.json_normalize(all_data)

        # --- 3. Build mapping ---
        mapping = (
            df_obs[['Site_Id', 'Parameter.ParameterCode']]
            .drop_duplicates()
        )

        station_params = (
            mapping
            .groupby('Site_Id')['Parameter.ParameterCode']
            .apply(lambda x: sorted(set(x)))
            .reset_index()
            .rename(columns={'Parameter.ParameterCode': 'Parameters'})
        )

        # --- 4. Merge ---
        df_full = df_sites.merge(station_params, on='Site_Id', how='left')

        # ✅ clean NaN → []
        df_full['Parameters'] = df_full['Parameters'].apply(
            lambda x: x if isinstance(x, list) else []
        )

        return df_full


if __name__ == '__main__':
    AQMS = aqms_api_class()

    df_full = AQMS.get_full_station_metadata()

    df_full.to_csv(
        r'W:\_gc_working_dir\StationMetadata.csv',
        index=False,
        encoding='utf-8'
    )