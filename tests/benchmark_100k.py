import os
import sys
import time
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from PySide6.QtWidgets import QApplication

app = QApplication.instance()
if app is None:
    app = QApplication([])

from src.engine.parquet_handler import ParquetHandler
from src.models.parquet_table_model import ParquetTableModel
from src.ui.data_grid_view import DataGridWidget


class TestBenchmark100k(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.test_dir = os.path.abspath("sample_data")
        os.makedirs(cls.test_dir, exist_ok=True)
        cls.parquet_100k_path = os.path.join(cls.test_dir, "benchmark_100k_rows.parquet")

        print("\n--- Generating 100,000 rows Parquet dataset ---")
        t0 = time.perf_counter()
        n = 100_000
        np.random.seed(42)
        
        df_100k = pd.DataFrame({
            "transaction_id": np.arange(1, n + 1, dtype=np.int64),
            "account_id": np.random.randint(10000, 99999, size=n, dtype=np.int32),
            "customer_name": np.random.choice(["Alice Smith", "Bob Jones", "Charlie Brown", "David Lee", "Eve Miller"], size=n),
            "amount": np.random.uniform(5.0, 5000.0, size=n).round(2),
            "status": np.random.choice(["COMPLETED", "PENDING", "FAILED", "REFUNDED"], size=n),
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="1min"),
            "is_flagged": np.random.choice([True, False], size=n, p=[0.02, 0.98]),
            "risk_score": np.random.choice([np.nan, 0.1, 0.5, 0.9, 0.99], size=n),
        })

        table = pa.Table.from_pandas(df_100k)
        pq.write_table(table, cls.parquet_100k_path, compression="snappy")
        t1 = time.perf_counter()
        print(f"Generated 100,000 rows in {t1 - t0:.3f}s. File size: {os.path.getsize(cls.parquet_100k_path) / 1024 / 1024:.2f} MB")

    def test_load_and_scroll_performance(self):
        print("\n--- Testing 100k Rows Load & UI Performance ---")
        t0 = time.perf_counter()
        df, schema, metadata = ParquetHandler.read_parquet(self.parquet_100k_path)
        t_read = time.perf_counter()
        print(f"1. Parquet Read Time: {t_read - t0:.4f}s ({len(df):,} rows)")
        self.assertEqual(len(df), 100_000)

        grid = DataGridWidget()
        t_grid_0 = time.perf_counter()
        grid.load_data(df, metadata)
        t_grid_1 = time.perf_counter()
        print(f"2. DataGrid Load & Sizing Time: {t_grid_1 - t_grid_0:.4f}s")
        self.assertLess(t_grid_1 - t_grid_0, 0.5, "100k load must take < 0.5s")

        # Test cell access time for 8,000 rendered cells (simulating rapid scrolling)
        model = grid.table_model
        t_render_0 = time.perf_counter()
        for r in range(1000):
            for c in range(8):
                idx = model.index(r, c)
                _ = model.data(idx, 0)  # DisplayRole
        t_render_1 = time.perf_counter()
        print(f"3. Virtualized 8,000 Cell Render Time: {t_render_1 - t_render_0:.4f}s")
        self.assertLess(t_render_1 - t_render_0, 0.35, "Rendering must take < 350ms for 8,000 cells")

    def test_vectorized_search_performance(self):
        print("\n--- Testing Vectorized Search across 100k Rows ---")
        grid = DataGridWidget()
        df, schema, metadata = ParquetHandler.read_parquet(self.parquet_100k_path)
        grid.load_data(df, metadata)

        t0 = time.perf_counter()
        grid._perform_search("REFUNDED", case_sensitive=False)
        t1 = time.perf_counter()
        match_count = len(grid._search_matches)
        print(f"Search across 800,000 cells for 'REFUNDED': {t1 - t0:.4f}s (found {match_count:,} matches)")
        self.assertGreater(match_count, 1000)
        self.assertLess(t1 - t0, 0.40, "Vectorized search across 100k rows must take < 400ms")

    def test_bulk_copy_paste_from_excel_sql(self):
        print("\n--- Testing Bulk Paste of 1,000 rows from Excel/SQL TSV ---")
        grid = DataGridWidget()
        df, schema, metadata = ParquetHandler.read_parquet(self.parquet_100k_path)
        grid.load_data(df, metadata)

        # Simulate 1,000 rows TSV copied from Excel or SQL Query Result
        simulated_tsv_matrix = []
        for i in range(1000):
            simulated_tsv_matrix.append([
                str(900000 + i),
                "55555",
                f"SQL User {i}",
                f"{123.45 + i:.2f}",
                "COMPLETED",
                "2025-06-01 12:00:00",
                "False",
                "0.12",
            ])

        model = grid.table_model
        t0 = time.perf_counter()
        rows_pasted, cols_pasted = model.paste_bulk_matrix(100, 0, simulated_tsv_matrix)
        t1 = time.perf_counter()
        print(f"Bulk pasted {rows_pasted:,} rows × {cols_pasted} cols into 100k dataset in {t1 - t0:.4f}s")
        self.assertEqual(rows_pasted, 1000)
        self.assertEqual(model.get_dataframe().iat[100, 2], "SQL User 0")
        self.assertEqual(model.get_dataframe().iat[100, 0], 900000)
        self.assertLess(t1 - t0, 1.0, "1,000 row batch paste must take < 1.0s")

    def test_statistics_on_large_selection(self):
        print("\n--- Testing Excel Stats on 5,000 cells ---")
        df, schema, metadata = ParquetHandler.read_parquet(self.parquet_100k_path)
        model = ParquetTableModel(df)

        indexes = [model.index(r, 3) for r in range(5000)]  # amount column
        t0 = time.perf_counter()
        stats = model.compute_stats(indexes)
        t1 = time.perf_counter()
        print(f"Calculated Count, Sum, Avg, Min, Max on 5,000 cells in {t1 - t0:.4f}s")
        print(f"Stats: Count={stats['count']:,}, Sum={stats['sum']:,.2f}, Avg={stats['avg']:,.2f}")
        self.assertEqual(stats["count"], 5000)
        self.assertTrue(stats["is_numeric"])
        self.assertLess(t1 - t0, 0.10, "Stats calculation must take < 100ms")


if __name__ == "__main__":
    unittest.main()
