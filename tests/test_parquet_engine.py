"""
Automated unit and integration tests for the Parquet Editor engine and data models.
"""
import os
import tempfile
import unittest
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

# Import application components
from src.engine.parquet_handler import ParquetHandler
from src.models.parquet_table_model import ParquetTableModel


class TestParquetEditor(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_parquet_path = os.path.join(self.temp_dir, "test_dataset.parquet")

        # Create rich test dataframe
        self.test_df = pd.DataFrame({
            "id": [1, 2, 3, 4, 5],
            "name": ["Alice", "Bob", "Charlie", "David", "Eve"],
            "score": [95.5, 82.0, 78.5, 91.0, np.nan],
            "is_active": [True, False, True, True, False],
            "created_at": pd.date_range("2025-01-01", periods=5, freq="D"),
        })

        table = pa.Table.from_pandas(self.test_df)
        pq.write_table(table, self.original_parquet_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_read_parquet_and_metadata(self):
        df, schema, metadata = ParquetHandler.read_parquet(self.original_parquet_path)
        self.assertEqual(len(df), 5)
        self.assertEqual(len(df.columns), 5)
        self.assertEqual(metadata["num_rows"], 5)
        self.assertEqual(metadata["num_cols"], 5)
        self.assertIn("score", metadata["columns"])
        self.assertEqual(metadata["columns"]["score"]["null_count"], 1)

    def test_table_model_data_and_editing(self):
        df, schema, _ = ParquetHandler.read_parquet(self.original_parquet_path)
        model = ParquetTableModel(df)

        self.assertEqual(model.rowCount(), 5)
        self.assertEqual(model.columnCount(), 5)
        self.assertFalse(model.is_dirty)

        # Edit cell (row 0, col 0 -> '100')
        idx = model.index(0, 0)
        success = model.setData(idx, "100")
        self.assertTrue(success)
        self.assertTrue(model.is_dirty)
        self.assertEqual(model.get_dataframe().iat[0, 0], 100)

        # Edit boolean cell (row 1, col 3 -> 'True')
        idx_bool = model.index(1, 3)
        self.assertTrue(model.setData(idx_bool, "True"))
        self.assertTrue(model.get_dataframe().iat[1, 3])

        # Edit float cell (row 4, col 2 -> '88.5' which was NaN)
        idx_float = model.index(4, 2)
        self.assertTrue(model.setData(idx_float, "88.5"))
        self.assertEqual(model.get_dataframe().iat[4, 2], 88.5)

    def test_insert_and_delete_rows(self):
        df, _, _ = ParquetHandler.read_parquet(self.original_parquet_path)
        model = ParquetTableModel(df)

        # Insert row at end
        self.assertTrue(model.insert_row())
        self.assertEqual(model.rowCount(), 6)

        # Delete row 0
        self.assertTrue(model.delete_rows([0]))
        self.assertEqual(model.rowCount(), 5)

    def test_statistics_calculation(self):
        df, _, _ = ParquetHandler.read_parquet(self.original_parquet_path)
        model = ParquetTableModel(df)

        # Select score column (col 2)
        indexes = [model.index(r, 2) for r in range(4)]  # rows 0..3 (scores: 95.5, 82.0, 78.5, 91.0)
        stats = model.compute_stats(indexes)

        self.assertEqual(stats["count"], 4)
        self.assertTrue(stats["is_numeric"])
        self.assertAlmostEqual(stats["sum"], 347.0)
        self.assertAlmostEqual(stats["avg"], 86.75)
        self.assertAlmostEqual(stats["min"], 78.5)
        self.assertAlmostEqual(stats["max"], 95.5)

    def test_non_destructive_save(self):
        df, schema, _ = ParquetHandler.read_parquet(self.original_parquet_path)
        model = ParquetTableModel(df)

        # Edit data
        model.setData(model.index(0, 1), "Alice Modified")

        edited_parquet_path = os.path.join(self.temp_dir, "test_dataset_edited.parquet")
        ParquetHandler.write_parquet(model.get_dataframe(), edited_parquet_path, schema)

        # Verify new file exists and contains modification
        self.assertTrue(os.path.exists(edited_parquet_path))
        edited_df, _, _ = ParquetHandler.read_parquet(edited_parquet_path)
        self.assertEqual(edited_df.iat[0, 1], "Alice Modified")

        # Verify original file remains completely untouched!
        orig_df, _, _ = ParquetHandler.read_parquet(self.original_parquet_path)
        self.assertEqual(orig_df.iat[0, 1], "Alice")

    def test_exports(self):
        df, _, _ = ParquetHandler.read_parquet(self.original_parquet_path)

        csv_path = os.path.join(self.temp_dir, "export.csv")
        self.assertTrue(ParquetHandler.export_csv(df, csv_path))
        self.assertTrue(os.path.exists(csv_path))

        xlsx_path = os.path.join(self.temp_dir, "export.xlsx")
        self.assertTrue(ParquetHandler.export_excel(df, xlsx_path))
        self.assertTrue(os.path.exists(xlsx_path))

        json_path = os.path.join(self.temp_dir, "export.json")
        self.assertTrue(ParquetHandler.export_json(df, json_path))
        self.assertTrue(os.path.exists(json_path))


if __name__ == "__main__":
    unittest.main()
