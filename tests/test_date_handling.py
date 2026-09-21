import os
import tempfile
import datetime
import unittest
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.engine.parquet_handler import ParquetHandler
from src.models.parquet_table_model import ParquetTableModel


class TestDateHandling(unittest.TestCase):

    def test_save_parquet_with_edited_date32(self):
        """Tests saving a Parquet file when a date32 column has edited string values."""
        schema = pa.schema([
            pa.field("investment_date", pa.date32()),
            pa.field("amount", pa.float64()),
        ])
        orig_table = pa.table({
            "investment_date": [datetime.date(2025, 12, 29), None, datetime.date(2027, 5, 23)],
            "amount": [100.5, 200.0, 300.0],
        }, schema=schema)

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, "test_dates.parquet")
            pq.write_table(orig_table, file_path)

            # Load file with ParquetHandler
            df, read_schema, metadata = ParquetHandler.read_parquet(file_path)

            # Create model and edit a cell in investment_date (visual row 0)
            model = ParquetTableModel(df)
            idx = model.index(0, 0)
            # Edit to a new date string
            success = model.setData(idx, "2026-06-15")
            self.assertTrue(success)

            edited_df = model.get_dataframe()
            saved_file = os.path.join(tmp_dir, "saved_dates.parquet")
            save_ok = ParquetHandler.write_parquet(edited_df, saved_file, read_schema)
            self.assertTrue(save_ok)

            # Read back and verify types and values
            reloaded_table = pq.read_table(saved_file)
            self.assertEqual(reloaded_table.schema.field("investment_date").type, pa.date32())
            
            reloaded_df = reloaded_table.to_pandas()
            self.assertEqual(reloaded_df["investment_date"].iloc[0], datetime.date(2026, 6, 15))
            self.assertTrue(pd.isna(reloaded_df["investment_date"].iloc[1]) or reloaded_df["investment_date"].iloc[1] is None)
            self.assertEqual(reloaded_df["investment_date"].iloc[2], datetime.date(2027, 5, 23))

    def test_save_mixed_dates_to_string_column(self):
        """Tests saving datetime.date objects to a string column without crashing."""
        schema = pa.schema([
            pa.field("date_str", pa.string()),
        ])
        df = pd.DataFrame({
            "date_str": [datetime.date(2025, 1, 1), "2025-02-02", None],
        })

        with tempfile.TemporaryDirectory() as tmp_dir:
            saved_file = os.path.join(tmp_dir, "saved_str_dates.parquet")
            save_ok = ParquetHandler.write_parquet(df, saved_file, schema)
            self.assertTrue(save_ok)

            reloaded = pq.read_table(saved_file)
            self.assertEqual(reloaded.schema.field("date_str").type, pa.string())
            reloaded_df = reloaded.to_pandas()
            self.assertEqual(reloaded_df["date_str"].iloc[0], "2025-01-01")
            self.assertEqual(reloaded_df["date_str"].iloc[1], "2025-02-02")
            self.assertTrue(pd.isna(reloaded_df["date_str"].iloc[2]) or reloaded_df["date_str"].iloc[2] is None)

    def test_add_date32_column_and_save(self):
        """Tests adding a new date32 column in the model and saving to parquet."""
        df = pd.DataFrame({
            "name": ["Alice", "Bob"],
        })
        model = ParquetTableModel(df)
        model.add_column("start_date", "date32", "2025-01-01")

        with tempfile.TemporaryDirectory() as tmp_dir:
            saved_file = os.path.join(tmp_dir, "added_date_col.parquet")
            save_ok = ParquetHandler.write_parquet(model.get_dataframe(), saved_file)
            self.assertTrue(save_ok)

            reloaded = pq.read_table(saved_file)
            reloaded_df = reloaded.to_pandas()
            self.assertIn("start_date", reloaded_df.columns)
            self.assertEqual(reloaded_df["start_date"].iloc[0], datetime.date(2025, 1, 1))


if __name__ == "__main__":
    unittest.main()
