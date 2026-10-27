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

    def test_apply_bulk_cell_edits_and_undo(self):
        """Tests ParquetTableModel.apply_bulk_cell_edits with type casting and unified undo."""
        df = pd.DataFrame({
            "col_str": ["A", "B", "C", "D"],
            "col_num": [1, 2, 3, 4],
        })
        model = ParquetTableModel(df)

        # Apply edits across multiple cells
        edits = [
            (0, 0, "Z"),
            (2, 0, "None"),  # Should be string "None"
            (1, 1, "99"),
            (3, 1, "<null>"), # Should be None
        ]
        count = model.apply_bulk_cell_edits(edits, description="Test Bulk Edit")
        self.assertEqual(count, 4)

        df_after = model.get_dataframe()
        self.assertEqual(df_after.iat[0, 0], "Z")
        self.assertEqual(df_after.iat[2, 0], "None")
        self.assertEqual(df_after.iat[1, 1], 99)
        self.assertTrue(pd.isna(df_after.iat[3, 1]))

        # Unified undo
        model.undo_stack.undo()
        df_undone = model.get_dataframe()
        self.assertEqual(df_undone.iat[0, 0], "A")
        self.assertEqual(df_undone.iat[2, 0], "C")
        self.assertEqual(df_undone.iat[1, 1], 2)
        self.assertEqual(df_undone.iat[3, 1], 4)

    def test_table_view_fill_down_and_fill_right(self):
        """Tests Fill Down (Ctrl+D) and Fill Right (Ctrl+R) in ExcelTableView."""
        from PySide6.QtCore import QItemSelection, QItemSelectionRange
        from src.ui.data_grid_view import DataGridWidget

        df = pd.DataFrame({
            "A": ["TopA", "x", "y"],
            "B": ["TopB", "x", "y"],
            "C": ["TopC", "x", "y"],
        })
        grid = DataGridWidget()
        grid.load_data(df, {"columns": {}})
        table = grid.table_view
        model = grid.table_model

        # 1. Test Fill Down on columns 0 and 1, rows 0..2
        sel_range = QItemSelection(model.index(0, 0), model.index(2, 1))
        table.selectionModel().select(sel_range, table.selectionModel().SelectionFlag.ClearAndSelect)

        table.fill_down()
        current_df = model.get_dataframe()
        self.assertEqual(current_df.iat[1, 0], "TopA")
        self.assertEqual(current_df.iat[2, 0], "TopA")
        self.assertEqual(current_df.iat[1, 1], "TopB")
        self.assertEqual(current_df.iat[2, 1], "TopB")
        # Column C should be untouched
        self.assertEqual(current_df.iat[1, 2], "x")

        # Undo fill down
        model.undo_stack.undo()
        self.assertEqual(model.get_dataframe().iat[1, 0], "x")

        # 2. Test Fill Right on row 0, columns 0..2
        sel_row_range = QItemSelection(model.index(0, 0), model.index(0, 2))
        table.selectionModel().select(sel_row_range, table.selectionModel().SelectionFlag.ClearAndSelect)

        table.fill_right()
        self.assertEqual(model.get_dataframe().iat[0, 1], "TopA")
        self.assertEqual(model.get_dataframe().iat[0, 2], "TopA")

    def test_paste_single_value_to_multiple_cells(self):
        """Tests 1-to-many paste into multiple selected cells."""
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtCore import QItemSelection
        from src.ui.data_grid_view import DataGridWidget

        df = pd.DataFrame({
            "col": ["1", "2", "3", "4"],
        })
        grid = DataGridWidget()
        grid.load_data(df, {"columns": {}})
        table = grid.table_view
        model = grid.table_model

        # Copy single value
        QGuiApplication.clipboard().setText("PastedValue")

        # Select rows 1, 2, 3
        sel_range = QItemSelection(model.index(1, 0), model.index(3, 0))
        table.selectionModel().select(sel_range, table.selectionModel().SelectionFlag.ClearAndSelect)

        table.paste_selection()
        current_df = model.get_dataframe()
        self.assertEqual(current_df.iat[0, 0], "1") # untouched
        self.assertEqual(current_df.iat[1, 0], "PastedValue")
        self.assertEqual(current_df.iat[2, 0], "PastedValue")
        self.assertEqual(current_df.iat[3, 0], "PastedValue")


if __name__ == "__main__":
    unittest.main()
