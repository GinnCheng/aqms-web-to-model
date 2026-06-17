from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, List

import pandas as pd
from qld_aqms_scraper import build_aqms_dataframe


class AQMSParquetStore:
    """
    A small helper for:
    - loading parquet
    - saving parquet
    - updating parquet with new AQMS rows

    Deduplication key:
        ["dataset_year", "resource_title"]
    """

    def __init__(
        self,
        parquet_path: str | Path,
        key_cols: Optional[List[str]] = None,
        engine: str = "pyarrow",
    ):
        self.parquet_path = Path(parquet_path)
        self.key_cols = key_cols or ["dataset_year", "resource_title"]
        self.engine = engine

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------
    def exists(self) -> bool:
        return self.parquet_path.exists()

    def load(self) -> pd.DataFrame:
        if not self.parquet_path.exists():
            return pd.DataFrame()
        return pd.read_parquet(self.parquet_path, engine=self.engine)

    def save(self, df: pd.DataFrame) -> pd.DataFrame:
        self._ensure_parent_dir()
        df_to_save = self._normalize_dataframe(df.copy())
        df_to_save.to_parquet(self.parquet_path, index=False, engine=self.engine)
        return df_to_save

    def update(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Update existing parquet with new rows from df using key_cols.
        If parquet doesn't exist, save df as new parquet.
        """
        df_new = self._normalize_dataframe(df.copy())

        if not self.parquet_path.exists():
            self.save(df_new)
            return df_new

        df_existing = self.load()
        df_existing = self._normalize_dataframe(df_existing)

        if df_existing.empty:
            self.save(df_new)
            return df_new

        # Align columns between old and new
        all_cols = self._union_columns(df_existing, df_new)
        df_existing = self._align_columns(df_existing, all_cols)
        df_new = self._align_columns(df_new, all_cols)

        # Ensure key columns exist
        missing_existing = [c for c in self.key_cols if c not in df_existing.columns]
        missing_new = [c for c in self.key_cols if c not in df_new.columns]
        if missing_existing or missing_new:
            raise ValueError(
                f"Key columns missing. "
                f"Missing in existing: {missing_existing}, "
                f"Missing in incoming: {missing_new}"
            )

        # Use anti-join to detect new rows
        existing_keys = df_existing[self.key_cols].drop_duplicates()

        merged = df_new.merge(
            existing_keys,
            on=self.key_cols,
            how="left",
            indicator=True
        )

        new_rows = merged[merged["_merge"] == "left_only"].drop(columns=["_merge"])

        if new_rows.empty:
            # No update required
            return df_existing

        final_df = pd.concat([df_existing, new_rows], ignore_index=True)
        final_df = final_df.drop_duplicates(subset=self.key_cols, keep="last").reset_index(drop=True)

        self.save(final_df)
        return final_df

    # --------------------------------------------------------
    # Internal helpers
    # --------------------------------------------------------
    def _ensure_parent_dir(self):
        self.parquet_path.parent.mkdir(parents=True, exist_ok=True)

    def _union_columns(self, df1: pd.DataFrame, df2: pd.DataFrame) -> List[str]:
        return list(dict.fromkeys(list(df1.columns) + list(df2.columns)))

    def _align_columns(self, df: pd.DataFrame, all_cols: List[str]) -> pd.DataFrame:
        out = df.copy()
        for c in all_cols:
            if c not in out.columns:
                out[c] = pd.NA
        return out[all_cols]

    def _normalize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Make object/list/dict columns comparable and parquet-friendly.
        """
        out = df.copy()

        for col in out.columns:
            if out[col].dtype == "object":
                out[col] = out[col].apply(self._normalize_cell)

        return out

    def _normalize_cell(self, value):
        if pd.isna(value):
            return pd.NA

        if isinstance(value, (list, dict)):
            try:
                return json.dumps(value, sort_keys=True, ensure_ascii=False)
            except Exception:
                return str(value)

        return value


def load_or_scrape_aqms(
    update: bool = False,
    parquet_path: str | Path = "data/qld_aqms_resources.parquet",
    years=[2020, 2021, 2022, 2023, 2024],
    query: str = "air quality monitoring",
    max_pages: int = 10,
    sleep_between_resources: float = 0.4,
    key_cols: Optional[List[str]] = None,
):
    """
    Main entry point.

    Behavior:
    - update=False:
        - if parquet exists -> load it
        - if parquet missing -> scrape, save, return
    - update=True:
        - always scrape
        - merge into existing parquet using key_cols
        - if parquet missing -> save scraped df
    """

    store = AQMSParquetStore(
        parquet_path=parquet_path,
        key_cols=key_cols or ["dataset_year", "resource_title"],
        engine="pyarrow",
    )

    if not update:
        if store.exists():
            return store.load()

        # parquet missing -> scrape and save
        df_scraped = build_aqms_dataframe(
            years=years,
            query=query,
            max_pages=max_pages,
            sleep_between_resources=sleep_between_resources,
        )
        return store.save(df_scraped)

    # update=True -> always scrape, then update parquet
    df_scraped = build_aqms_dataframe(
        years=years,
        query=query,
        max_pages=max_pages,
        sleep_between_resources=sleep_between_resources,
    )
    return store.update(df_scraped)