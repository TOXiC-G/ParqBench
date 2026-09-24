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
    def _coerce_series_for_arrow_field(series: pd.Series, field: Optional[pa.Field] = None) -> pa.Array:
        """Safely coerces a Pandas Series into a PyArrow Array matching the target field type."""
        import datetime

        if field is None:
            # Check if series contains datetime.date objects or mixed dates/strings
            non_nulls = [v for v in series if pd.notna(v) and v is not None]
            has_dates = any(isinstance(v, (datetime.date, datetime.datetime, pd.Timestamp)) for v in non_nulls)
            has_strs = any(isinstance(v, str) for v in non_nulls)
            if has_dates and has_strs:
                try:
                    dt_series = pd.to_datetime(series, errors="coerce")
                    date_vals = [d.date() if pd.notna(d) else None for d in dt_series]
                    return pa.array(date_vals, type=pa.date32())
                except Exception:
                    pass
            try:
                return pa.Array.from_pandas(series)
            except Exception:
                return pa.array([str(v) if pd.notna(v) and v is not None else None for v in series])

        arrow_type = field.type

        try:
            # 1. Date types: date32, date64
            if pa.types.is_date(arrow_type):
                dt_series = pd.to_datetime(series, errors="coerce")
                date_vals = [d.date() if pd.notna(d) else None for d in dt_series]
                return pa.array(date_vals, type=arrow_type)

            # 2. Timestamp types
            elif pa.types.is_timestamp(arrow_type):
                dt_series = pd.to_datetime(series, errors="coerce")
                return pa.Array.from_pandas(dt_series, type=arrow_type)

            # 3. String / Binary types
            elif pa.types.is_string(arrow_type) or pa.types.is_large_string(arrow_type) or pa.types.is_binary(arrow_type) or pa.types.is_large_binary(arrow_type):
                str_vals = [
                    (v.isoformat() if hasattr(v, "isoformat") else str(v))
                    if pd.notna(v) and v is not None else None
                    for v in series
                ]
                return pa.array(str_vals, type=arrow_type)

            # 4. Integer types
            elif pa.types.is_integer(arrow_type):
                def _to_int(v):
                    try:
                        if pd.isna(v) or v is None or str(v).strip() == "":
                            return None
                        return int(round(float(v)))
                    except Exception:
                        return None
                return pa.array([_to_int(v) for v in series], type=arrow_type)

            # 5. Floating point types
            elif pa.types.is_floating(arrow_type):
                def _to_float(v):
                    try:
                        if pd.isna(v) or v is None or str(v).strip() == "":
                            return None
                        return float(v)
                    except Exception:
                        return None
                return pa.array([_to_float(v) for v in series], type=arrow_type)

            # 6. Boolean types
            elif pa.types.is_boolean(arrow_type):
                def _to_bool(v):
                    if pd.isna(v) or v is None:
                        return None
                    if isinstance(v, bool):
                        return v
                    s = str(v).strip().lower()
                    if s in ("true", "1", "t", "yes", "y"):
                        return True
                    if s in ("false", "0", "f", "no", "n"):
                        return False
                    return None
                return pa.array([_to_bool(v) for v in series], type=arrow_type)

            # 7. Decimal types (decimal128, decimal256)
            elif pa.types.is_decimal(arrow_type):
                import decimal
                scale = getattr(arrow_type, "scale", 2)
                quant = decimal.Decimal(10) ** -scale if scale > 0 else decimal.Decimal(1)

                def _to_decimal(v):
                    if pd.isna(v) or v is None or str(v).strip() == "":
                        return None
                    try:
                        if isinstance(v, decimal.Decimal):
                            return v.quantize(quant)
                        elif isinstance(v, (int, float)):
                            return decimal.Decimal(str(round(float(v), scale))).quantize(quant)
                        else:
                            cleaned = str(v).strip().replace("$", "").replace(",", "")
                            return decimal.Decimal(cleaned).quantize(quant)
                    except Exception:
                        return None

                return pa.array([_to_decimal(v) for v in series], type=arrow_type)

            # 8. Default fallback with explicit type
            return pa.Array.from_pandas(series, type=arrow_type)

        except Exception:
            try:
                arr = pa.Array.from_pandas(series)
                return arr.cast(arrow_type)
            except Exception:
                try:
                    return pa.Array.from_pandas(series)
                except Exception:
                    return pa.array([str(v) if pd.notna(v) and v is not None else None for v in series])

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

        arrays = []
        fields = []

        try:
            if original_schema is not None:
                for col in df.columns:
                    series = df[col]
                    field = original_schema.field(col) if col in original_schema.names else None
                    arr = ParquetHandler._coerce_series_for_arrow_field(series, field)
                    if field is not None:
                        fields.append(field)
                    else:
                        fields.append(pa.field(str(col), arr.type))
                    arrays.append(arr)

                target_schema = pa.schema(fields, metadata=original_schema.metadata)
                table = pa.Table.from_arrays(arrays, schema=target_schema)
            else:
                for col in df.columns:
                    series = df[col]
                    arr = ParquetHandler._coerce_series_for_arrow_field(series, None)
                    fields.append(pa.field(str(col), arr.type))
                    arrays.append(arr)
                table = pa.Table.from_arrays(arrays, schema=pa.schema(fields))

        except Exception:
            # Fallback to standard conversion if column-by-column assembly encounters unexpected error
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
