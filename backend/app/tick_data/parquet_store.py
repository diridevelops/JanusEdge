"""Parquet read/write helpers backed by MinIO."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from app.storage import get_client, get_market_data_bucket


class MarketDataParquetStore:
    """Persist market-data Parquet objects in MinIO."""

    def write_dataframe(
        self,
        object_key: str,
        frame: pd.DataFrame,
    ) -> int:
        """Write a DataFrame to Parquet and return the stored byte size."""

        buffer = BytesIO()
        table = pa.Table.from_pandas(
            frame,
            preserve_index=False,
        )
        pq.write_table(
            table,
            buffer,
            compression="snappy",
        )

        byte_size = buffer.tell()
        buffer.seek(0)
        client = get_client()
        client.put_object(
            get_market_data_bucket(),
            object_key,
            buffer,
            length=byte_size,
            content_type="application/x-parquet",
        )
        return byte_size

    def read_dataframe(self, object_key: str) -> pd.DataFrame:
        """Read a Parquet object from MinIO into a DataFrame."""

        client = get_client()
        response = client.get_object(
            get_market_data_bucket(),
            object_key,
        )
        try:
            payload = response.read()
        finally:
            if hasattr(response, "close"):
                response.close()
            if hasattr(response, "release_conn"):
                response.release_conn()

        if not payload:
            return pd.DataFrame()

        return pq.read_table(BytesIO(payload)).to_pandas()