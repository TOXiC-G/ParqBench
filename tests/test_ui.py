"""
Headless UI tests verifying MainWindow, FileExplorer, and DataGrid widgets with PySide6.
"""
import os
import unittest
import pandas as pd
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Ensure QApplication instance exists
app = QApplication.instance()
if app is None:
    app = QApplication([])

from src.ui.main_window import MainWindow
from src.ui.file_explorer import FileExplorerWidget
from src.ui.data_grid_view import DataGridWidget
from src.engine.parquet_handler import ParquetHandler


class TestUIComponents(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.sample_path = os.path.abspath("sample_data/sales_orders.parquet")

    def test_main_window_creation(self):
        window = MainWindow()
        self.assertIsNotNone(window)
        self.assertIsNotNone(window.file_explorer)
        self.assertIsNotNone(window.data_grid)
        window.close()

    def test_load_sample_file(self):
        window = MainWindow(initial_file=self.sample_path)
        self.assertEqual(window._current_file_path, self.sample_path)
        self.assertEqual(window.data_grid.table_model.rowCount(), 250)
        self.assertEqual(window.data_grid.table_model.columnCount(), 9)
        self.assertFalse(window.data_grid.is_dirty)

        # Test search
        window.data_grid._perform_search("Laptop", case_sensitive=False)
        self.assertGreater(len(window.data_grid._search_matches), 0)

        # Test cell edit
        idx = window.data_grid.table_model.index(0, 3)  # product column
        window.data_grid.table_model.setData(idx, "Super Laptop X")
        # Mark clean so QMessageBox doesn't block headlessly on close
        window.data_grid.mark_saved()
        window.close()

    def test_file_explorer_filtering(self):
        explorer = FileExplorerWidget(os.getcwd())
        self.assertIsNotNone(explorer)
        self.assertEqual(explorer.model.nameFilters(), ["*.parquet", "*.PARQUET"])


if __name__ == "__main__":
    unittest.main()
