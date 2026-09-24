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
        self.assertIsNotNone(window.tab_widget)
        window.close()

    def test_load_sample_file(self):
        window = MainWindow(initial_file=self.sample_path)
        grid = window._current_grid()
        self.assertIsNotNone(grid)
        self.assertEqual(grid.table_model.rowCount(), 250)
        self.assertEqual(grid.table_model.columnCount(), 9)
        self.assertFalse(grid.is_dirty)

        # Test search
        grid._perform_search("Laptop", case_sensitive=False)
        self.assertGreater(len(grid._search_matches), 0)

        # Test cell edit
        idx = grid.table_model.index(0, 3)  # product column
        grid.table_model.setData(idx, "Super Laptop X")
        # Mark clean so QMessageBox doesn't block headlessly on close
        grid.mark_saved()
        window.close()

    def test_file_explorer_filtering(self):
        explorer = FileExplorerWidget(os.getcwd())
        self.assertIsNotNone(explorer)
        self.assertEqual(explorer.model.nameFilters(), ["*.parquet", "*.PARQUET"])

    def test_file_explorer_resizable_columns(self):
        from PySide6.QtWidgets import QHeaderView
        explorer = FileExplorerWidget(os.getcwd())
        header = explorer.tree_view.header()

        # Columns must be Interactive (not Stretch) so user can drag and resize
        for i in range(4):
            self.assertEqual(header.sectionResizeMode(i), QHeaderView.ResizeMode.Interactive)
        self.assertFalse(header.stretchLastSection())

        # Test manual column resizing
        header.resizeSection(0, 350)
        self.assertEqual(header.sectionSize(0), 350)

        # Test reset column widths
        explorer._reset_column_widths()
        self.assertEqual(header.sectionSize(0), 240)
        self.assertEqual(header.sectionSize(1), 75)

        # Test autofit
        explorer._autofit_columns()
        self.assertGreaterEqual(header.sectionSize(0), 180)

    def test_scrollbar_styling_rules(self):
        from src.ui.styles import MODERN_DARK_THEME, MODERN_LIGHT_THEME
        for theme in [MODERN_DARK_THEME, MODERN_LIGHT_THEME]:
            self.assertIn("QScrollBar::add-page", theme)
            self.assertIn("QScrollBar::sub-page", theme)
            self.assertIn("QScrollBar::handle", theme)
            self.assertIn("QScrollBar::corner", theme)

    def test_pagination_spinbox_no_buttons(self):
        from src.ui.pagination_bar import PaginationBar
        from PySide6.QtWidgets import QSpinBox
        pb = PaginationBar()
        self.assertEqual(pb.spin_page.buttonSymbols(), QSpinBox.ButtonSymbols.NoButtons)

    def test_icon_buttons_have_icons(self):
        from src.ui.search_toolbar import SearchToolbar
        explorer = FileExplorerWidget(os.getcwd())
        self.assertFalse(explorer.btn_refresh.icon().isNull())
        self.assertEqual(explorer.btn_refresh.objectName(), "iconBtn")

        st = SearchToolbar()
        self.assertFalse(st.btn_prev.icon().isNull())
        self.assertFalse(st.btn_next.icon().isNull())
        self.assertFalse(st.btn_close.icon().isNull())
        self.assertEqual(st.btn_prev.objectName(), "iconBtn")
        self.assertEqual(st.btn_next.objectName(), "iconBtn")
        self.assertEqual(st.btn_close.objectName(), "iconBtn")

    def test_shift_wheel_horizontal_scroll(self):
        from PySide6.QtGui import QWheelEvent
        from PySide6.QtCore import QPoint, QPointF
        window = MainWindow(initial_file=self.sample_path)
        grid = window._current_grid()
        tv = grid.table_view
        h_bar = tv.horizontalScrollBar()

        init_val = h_bar.value()
        # Simulate Shift + wheel down
        event = QWheelEvent(
            QPointF(50, 50),
            QPointF(50, 50),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ShiftModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False
        )
        tv.wheelEvent(event)
        self.assertGreater(h_bar.value(), init_val)
        window.close()


if __name__ == "__main__":
    unittest.main()


