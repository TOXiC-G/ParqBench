"""
Parquet Data Handling Engine.
Handles loading and saving of Parquet files with strict type and schema preservation.
"""
from __future__ import annotations

import os
from typing import Dict, Any, Tuple, Optional
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


class ParquetHandler:
    """Provides methods for reading and writing Parquet files while preserving schema and data types."""

    @staticmethod
    def read_parquet(file_path: str) -> Tuple[pd.DataFrame, pa.Schema, Dict[str, Any]]:
        """
        Reads a Parquet file, extracting DataFrame, PyArrow Schema, and file metadata.
        
        Args:
            file_path: Absolute or relative path to the .parquet file.
            
        Returns:
            Tuple of (pd.DataFrame, pa.Schema, Dict with metadata and column stats)
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Read PyArrow Table directly to capture schema & metadata
        parquet_file = pq.ParquetFile(file_path)
        table = parquet_file.read()
        schema = table.schema

        # Convert to Pandas DataFrame preserving Arrow dtypes or appropriate nullable types
        df = table.to_pandas(types_mapper=None)

        # Build column metadata dictionary
        num_rows = table.num_rows
        num_cols = table.num_columns
        total_size_bytes = os.path.getsize(file_path)

        col_details = {}
        for col_name in df.columns:
            arrow_field = schema.field(col_name) if col_name in schema.names else None
            arrow_type_str = str(arrow_field.type) if arrow_field else str(df[col_name].dtype)
            pandas_dtype_str = str(df[col_name].dtype)
            null_count = int(df[col_name].isna().sum())

            col_details[col_name] = {
                "arrow_type": arrow_type_str,
                "pandas_dtype": pandas_dtype_str,
                "nullable": arrow_field.nullable if arrow_field else True,
                "null_count": null_count,
            }

        metadata = {
            "file_path": file_path,
            "file_name": os.path.basename(file_path),
            "num_rows": num_rows,
            "num_cols": num_cols,
            "file_size_bytes": total_size_bytes,
            "num_row_groups": parquet_file.num_row_groups,
            "columns": col_details,
            "custom_metadata": {
                k.decode("utf-8", errors="replace"): v.decode("utf-8", errors="replace")
                for k, v in (schema.metadata or {}).items()
            } if schema.metadata else {},
        }

        return df, schema, metadata

    @staticmethod
    def write_parquet(
        df: pd.DataFrame,
        dest_path: str,
        original_schema: Optional[pa.Schema] = None,
        compression: str = "snappy",
    ) -> bool:
        """
        Writes a DataFrame back to a Parquet file, casting to original schema types where possible.
        
        Args:
            df: The DataFrame to write.
            dest_path: Destination .parquet file path.
            original_schema: Optional original PyArrow schema to preserve exact types.
            compression: Parquet compression codec (default 'snappy').
            
        Returns:
            True if write was successful.
        """
        # Ensure destination directory exists
        os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)

        # Convert DataFrame to PyArrow Table
        if original_schema is not None:
            # Build target schema matching current df columns
            fields = []
            for col in df.columns:
                if col in original_schema.names:
                    fields.append(original_schema.field(col))
                else:
                    # Infer new column type from DataFrame
                    inferred_table = pa.Table.from_pandas(df[[col]])
                    fields.append(inferred_table.schema.field(col))
            
            target_schema = pa.schema(fields, metadata=original_schema.metadata)
            
            try:
                table = pa.Table.from_pandas(df, schema=target_schema, preserve_index=False)
            except Exception:
                # Fallback to standard conversion if strict casting fails
                table = pa.Table.from_pandas(df, preserve_index=False)
        else:
            table = pa.Table.from_pandas(df, preserve_index=False)

        # Write to destination parquet file
        pq.write_table(table, dest_path, compression=compression)
        return True

    @staticmethod
    def export_csv(df: pd.DataFrame, dest_path: str) -> bool:
        """Exports DataFrame to CSV format."""
        df.to_csv(dest_path, index=False)
        return True

    @staticmethod
    def export_excel(df: pd.DataFrame, dest_path: str) -> bool:
        """Exports DataFrame to Excel (.xlsx) format."""
        df.to_excel(dest_path, index=False, engine="openpyxl")
        return True

    @staticmethod
    def export_json(df: pd.DataFrame, dest_path: str) -> bool:
        """Exports DataFrame to JSON format."""
        df.to_json(dest_path, orient="records", date_format="iso", indent=2)
        return True
