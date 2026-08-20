"""
Tests for Advanced Features: Filtering, Pagination, Column Visibility, and Cell Delegate.
"""
import os
import sys
import unittest
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

app = QApplication.instance()
if app is None:
    app = QApplication([])

from src.models.parquet_table_model import ParquetTableModel
from src.ui.cell_delegate import ParquetCellDelegate
from src.ui.filter_dialog import ColumnFilterDialog
from src.ui.column_manager_dialog import ColumnManagerDialog
from src.ui.data_grid_view import DataGridWidget
from src.engine.parquet_handler import ParquetHandler


class TestAdvancedFeatures(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)
        self.df = pd.DataFrame({
            "id": np.arange(1, 101),
            "category": np.random.choice(["Electronics", "Clothing", "Home", "Books"], size=100),
            "price": np.random.uniform(10.0, 500.0, size=100).round(2),
            "in_stock": np.random.choice([True, False], size=100, p=[0.8, 0.2]),
            "score": np.random.choice([1.0, 2.5, 4.0, 5.0, np.nan], size=100),
        })
        self.model = ParquetTableModel(self.df)

    def test_pagination_defaults_and_navigation(self):
        # Default page size is 250 (so 100 rows fits in 1 page)
        self.assertEqual(self.model.rowCount(), 100)

        # Set page size to 25 rows -> 4 pages
        self.model.set_page_size(25)
        self.assertEqual(self.model.rowCount(), 25)
        self.assertEqual(self.model.current_page, 1)

        # Navigate to page 2 (rows 25..49)
        self.model.set_page(2)
        self.assertEqual(self.model.current_page, 2)
        self.assertEqual(self.model.rowCount(), 25)

        # Cell data at page 2, row 0 corresponds to underlying row 25 (id=26)
        idx = self.model.index(0, 0)
        self.assertEqual(self.model.data(idx, Qt.ItemDataRole.EditRole), "26")

        # Disable pagination (size = -1)
        self.model.set_page_size(-1)
        self.assertEqual(self.model.rowCount(), 100)

    def test_text_and_categorical_filtering(self):
        # Filter category to 'Electronics' only
        self.model.set_filter("category", {
            "type": "values",
            "values": ["Electronics"],
            "include_null": False,
            "description": "category in (1 value)",
        })

        filtered_count = self.model.get_total_filtered_rows()
        expected_count = int((self.df["category"] == "Electronics").sum())
        self.assertEqual(filtered_count, expected_count)

        # Clear filter
        self.model.remove_filter("category")
        self.assertEqual(self.model.get_total_filtered_rows(), 100)

    def test_numeric_condition_filtering(self):
        # Filter price >= 250.0
        self.model.set_filter("price", {
            "type": "condition",
            "op": ">=",
            "val1": "250.0",
            "description": "price >= 250.0",
        })

        expected_count = int((self.df["price"] >= 250.0).sum())
        self.assertEqual(self.model.get_total_filtered_rows(), expected_count)

        # Filter score IS NULL
        self.model.set_filter("score", {
            "type": "condition",
            "op": "null",
            "description": "score is null",
        })

        combined_expected = int(((self.df["price"] >= 250.0) & (self.df["score"].isna())).sum())
        self.assertEqual(self.model.get_total_filtered_rows(), combined_expected)

        # Clear all
        self.model.clear_all_filters()
        self.assertEqual(self.model.get_total_filtered_rows(), 100)

    def test_column_visibility_preserves_exports_and_dataframe(self):
        grid = DataGridWidget()
        metadata = {"file_name": "test.parquet", "num_rows": 100, "num_cols": 5}
        grid.load_data(self.df, metadata)

        # Hide "category" and "in_stock" in Viewport
        grid.set_hidden_columns({"category", "in_stock"})
        self.assertTrue(grid.table_view.isColumnHidden(1)) # category
        self.assertTrue(grid.table_view.isColumnHidden(3)) # in_stock
        self.assertFalse(grid.table_view.isColumnHidden(0)) # id is visible

        # Crucial Requirement: Underlying DataFrame and exports MUST preserve ALL columns intact!
        exported_df = grid.get_dataframe()
        self.assertEqual(len(exported_df.columns), 5)
        self.assertIn("category", exported_df.columns)
        self.assertIn("in_stock", exported_df.columns)

    def test_header_data_tooltips_and_indicators(self):
        # Check header data tooltip
        tooltip = self.model.headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
        self.assertIn("Column Details", tooltip)
        self.assertIn("id", tooltip)
        self.assertIn("int", tooltip.lower())

        # Sort column 0 Ascending
        self.model.sort(0, Qt.SortOrder.AscendingOrder)
        header_text = self.model.headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        self.assertIn("▲", header_text)

        # Apply filter -> header shows 🔍 indicator
        self.model.set_filter("id", {"type": "condition", "op": ">", "val1": "10"})
        header_text_filtered = self.model.headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        self.assertIn("🔍", header_text_filtered)


if __name__ == "__main__":
    unittest.main()
