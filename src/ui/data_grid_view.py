"""
Data Grid View Widget (Excel-like spreadsheet interface) — v2.
Adds: Undo/Redo wiring, Column Schema Management (Add/Rename/Delete),
Formula Expression Builder integration, full context menus.
"""
from __future__ import annotations

from typing import List, Tuple, Optional, Set, Dict, Any
import pandas as pd
import numpy as np
from PySide6.QtCore import Qt, Signal, QModelIndex, QItemSelectionModel
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableView,
    QHeaderView,
    QPushButton,
    QLabel,
    QMenu,
    QMessageBox,
    QAbstractItemView,
)
from PySide6.QtGui import QKeySequence, QGuiApplication, QCursor, QKeyEvent, QWheelEvent, QUndoStack

from src.models.parquet_table_model import ParquetTableModel
from src.ui.cell_delegate import ParquetCellDelegate
from src.ui.search_toolbar import SearchToolbar
from src.ui.filter_dialog import ColumnFilterDialog
from src.ui.active_filters_bar import ActiveFiltersBar
from src.ui.column_manager_dialog import ColumnManagerDialog
from src.ui.pagination_bar import PaginationBar
from src.ui.schema_dialog import SchemaDialog
from src.ui.column_schema_dialogs import AddColumnDialog, RenameColumnDialog
from src.ui.formula_dialog import FormulaBuilderDialog
from src.ui.parquet_diff import WorkingCopyDiffDialog


class ExcelTableView(QTableView):
    """Custom QTableView supporting Excel-like shortcuts (Ctrl+C, Ctrl+V, Delete)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )

        self.setItemDelegate(ParquetCellDelegate(self))

        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        self.horizontalHeader().setSectionsMovable(True)
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().setHighlightSections(True)
        self.horizontalHeader().setSectionsClickable(True)
        self.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.verticalHeader().setDefaultSectionSize(30)

    def keyPressEvent(self, event: QKeyEvent):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            event.accept()
            return
        elif event.matches(QKeySequence.StandardKey.Paste):
            self.paste_selection()
            event.accept()
            return
        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.clear_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            delta = event.angleDelta().y() or event.angleDelta().x()
            if delta != 0:
                h_bar = self.horizontalScrollBar()
                num_steps = delta / 120
                scroll_amount = int(-num_steps * max(40, h_bar.singleStep() * 3))
                h_bar.setValue(h_bar.value() + scroll_amount)
                event.accept()
                return
        super().wheelEvent(event)

    def copy_selection(self):
        selection = self.selectionModel().selectedIndexes()
        if not selection:
            return

        rows = sorted(set(idx.row() for idx in selection))
        cols = sorted(set(idx.column() for idx in selection))

        model = self.model()
        row_strings = []
        for r in rows:
            col_vals = []
            for c in cols:
                idx = model.index(r, c)
                if idx in selection:
                    val = model.data(idx, Qt.ItemDataRole.EditRole)
                    col_vals.append(str(val) if val is not None else "")
                else:
                    col_vals.append("")
            row_strings.append("\t".join(col_vals))

        QGuiApplication.clipboard().setText("\n".join(row_strings))

    def paste_selection(self):
        import csv, io
        text = QGuiApplication.clipboard().text()
        if not text:
            return

        selection = self.selectionModel().selectedIndexes()
        start_row = min(idx.row() for idx in selection) if selection else 0
        start_col = min(idx.column() for idx in selection) if selection else 0

        delimiter = "\t" if "\t" in text else ","
        try:
            reader = csv.reader(io.StringIO(text), delimiter=delimiter)
            lines = list(reader)
        except Exception:
            lines = [line.split("\t") for line in text.splitlines()]
            matrix = lines

        matrix = lines
        if not matrix:
            return

        model = self.model()
        if hasattr(model, "paste_bulk_matrix"):
            model.paste_bulk_matrix(start_row, start_col, matrix)

    def clear_selection(self):
        selection = self.selectionModel().selectedIndexes()
        if not selection:
            return
        model = self.model()
        for idx in selection:
            model.setData(idx, "", Qt.ItemDataRole.EditRole)


class DataGridWidget(QWidget):
    """Container widget housing the data table view, filter dialogs, active filters bar, and pagination."""

    data_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_metadata: Dict[str, Any] = {}
        self._hidden_columns: Set[str] = set()
        self._search_matches: List[Tuple[int, int]] = []
        self._search_match_idx: int = -1

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Top Action Toolbar
        top_bar = QWidget()
        top_bar.setStyleSheet("background-color: #1a1a20; border-bottom: 1px solid #2d2d34;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(8, 6, 8, 6)
        top_layout.setSpacing(6)

        self.lbl_file_title = QLabel("No Parquet file loaded")
        self.lbl_file_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #107c41;")
        top_layout.addWidget(self.lbl_file_title)

        top_layout.addStretch(1)

        self.btn_search = QPushButton("🔍 Find (Ctrl+F)")
        self.btn_search.clicked.connect(self._toggle_search_toolbar)
        top_layout.addWidget(self.btn_search)

        self.btn_col_view = QPushButton("👁️ Columns View")
        self.btn_col_view.setToolTip("Show or hide columns from the current view")
        self.btn_col_view.clicked.connect(self._open_column_manager)
        top_layout.addWidget(self.btn_col_view)

        self.btn_add_row = QPushButton("➕ Add Row")
        self.btn_add_row.setToolTip("Append new row at end")
        self.btn_add_row.clicked.connect(self._add_row)
        top_layout.addWidget(self.btn_add_row)

        self.btn_del_row = QPushButton("🗑️ Delete Row(s)")
        self.btn_del_row.setToolTip("Delete selected rows")
        self.btn_del_row.clicked.connect(self._delete_selected_rows)
        top_layout.addWidget(self.btn_del_row)

        self.btn_formula = QPushButton("𝑓 Formula")
        self.btn_formula.setToolTip("Apply a formula or expression to compute a column")
        self.btn_formula.clicked.connect(self._open_formula_builder)
        top_layout.addWidget(self.btn_formula)

        self.btn_schema = QPushButton("📊 Schema & Types")
        self.btn_schema.setToolTip("View column types and metadata")
        self.btn_schema.clicked.connect(self._show_schema_dialog)
        top_layout.addWidget(self.btn_schema)

        layout.addWidget(top_bar)

        # 2. Search Toolbar
        self.search_toolbar = SearchToolbar(self)
        self.search_toolbar.setVisible(False)
        self.search_toolbar.search_requested.connect(self._perform_search)
        self.search_toolbar.navigate_match.connect(self._navigate_search_match)
        self.search_toolbar.jump_to_row_requested.connect(self._jump_to_row)
        self.search_toolbar.closed.connect(lambda: self.search_toolbar.setVisible(False))
        layout.addWidget(self.search_toolbar)

        # 3. Active Filters Panel Bar
        self.active_filters_bar = ActiveFiltersBar(self)
        self.active_filters_bar.filter_removed.connect(self._remove_filter)
        self.active_filters_bar.filter_edit_requested.connect(self._open_filter_dialog_for_column)
        self.active_filters_bar.clear_all_requested.connect(self._clear_all_filters)
        layout.addWidget(self.active_filters_bar)

        # 4. Table View & Model
        self.table_view = ExcelTableView(self)
        self.table_model = ParquetTableModel(parent=self)

        self.table_model.dataModified.connect(self._on_model_modified)
        self.table_model.filterChanged.connect(self._on_filter_changed)
        self.table_model.paginationChanged.connect(self._on_pagination_state_changed)
        self.table_view.setModel(self.table_model)

        self.table_view.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table_view.horizontalHeader().customContextMenuRequested.connect(self._show_header_context_menu)

        self.table_view.selectionModel().selectionChanged.connect(self._update_stats_bar)
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._show_context_menu)

        layout.addWidget(self.table_view, 1)

        # 5. Pagination Bar
        self.pagination_bar = PaginationBar(default_page_size=250, parent=self)
        self.pagination_bar.page_changed.connect(self.table_model.set_page)
        self.pagination_bar.page_size_changed.connect(self.table_model.set_page_size)
        self.pagination_bar.pagination_toggled.connect(self._on_pagination_toggled)
        layout.addWidget(self.pagination_bar)

        # 6. Bottom Stats Bar
        stats_bar = QWidget()
        stats_bar.setStyleSheet("background-color: #121216; border-top: 1px solid #202028; padding: 2px;")
        stats_layout = QHBoxLayout(stats_bar)
        stats_layout.setContentsMargins(10, 2, 10, 2)
        stats_layout.setSpacing(12)

        self.lbl_dims = QLabel("0 rows, 0 columns")
        self.lbl_dims.setStyleSheet("color: #8a8a9a; font-size: 11px;")
        stats_layout.addWidget(self.lbl_dims)

        stats_layout.addStretch(1)

        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: 500;")
        stats_layout.addWidget(self.lbl_stats)

        layout.addWidget(stats_bar)

    # -------------------------------------------------------------------------
    # Public Methods
    # -------------------------------------------------------------------------

    def load_data(self, df: pd.DataFrame, metadata: dict):
        self._current_metadata = metadata
        self._hidden_columns.clear()
        self.table_model.set_dataframe(df)

        file_name = metadata.get("file_name", "Parquet Data")
        row_count = len(df)
        col_count = len(df.columns)
        self.lbl_file_title.setText(f"📄 {file_name}")
        self.lbl_dims.setText(f"{row_count:,} total rows × {col_count} columns")
        self.search_toolbar.set_max_rows(row_count)

        sample_df = df.head(100)
        for c, col_name in enumerate(df.columns):
            max_char_len = len(str(col_name))
            if not sample_df.empty:
                col_sample_max = sample_df[col_name].astype(str).str.len().max()
                if not pd.isna(col_sample_max):
                    max_char_len = max(max_char_len, int(col_sample_max))
            approx_width = max(90, min(int(max_char_len * 9.5) + 32, 380))
            self.table_view.setColumnWidth(c, approx_width)
            self.table_view.setColumnHidden(c, False)

        self.pagination_bar.update_pagination(row_count)
        self.active_filters_bar.update_filters({})

        self.table_view.selectionModel().selectionChanged.connect(self._update_stats_bar)
        self._update_stats_bar()

    def get_dataframe(self) -> pd.DataFrame:
        return self.table_model.get_dataframe()

    def mark_saved(self):
        self.table_model.mark_clean()

    @property
    def is_dirty(self) -> bool:
        return self.table_model.is_dirty

    @property
    def undo_stack(self) -> QUndoStack:
        return self.table_model.undo_stack

    def open_find(self):
        self.search_toolbar.setVisible(True)
        self.search_toolbar.focus_search()

    def set_hidden_columns(self, hidden_cols: Set[str]):
        self._hidden_columns = set(hidden_cols)
        df = self.table_model.get_dataframe()
        for c, col_name in enumerate(df.columns):
            self.table_view.setColumnHidden(c, col_name in self._hidden_columns)

    # -------------------------------------------------------------------------
    # Filtering, Sorting & Visibility Slots
    # -------------------------------------------------------------------------

    def _open_filter_dialog_for_column(self, col_name: str):
        df = self.table_model.get_dataframe()
        if col_name not in df.columns:
            return
        current_f = self.table_model.active_filters.get(col_name)
        dlg = ColumnFilterDialog(col_name, df[col_name], current_filter=current_f, parent=self)
        if dlg.exec():
            res = dlg.get_filter()
            if res:
                self.table_model.set_filter(col_name, res)
                self.active_filters_bar.update_filters(self.table_model.active_filters)

    def _remove_filter(self, col_name: str):
        self.table_model.remove_filter(col_name)
        self.active_filters_bar.update_filters(self.table_model.active_filters)

    def _clear_all_filters(self):
        self.table_model.clear_all_filters()
        self.active_filters_bar.update_filters({})

    def _on_filter_changed(self, filtered_count: int):
        total_rows = len(self.table_model.get_dataframe())
        self.pagination_bar.update_pagination(filtered_count)
        if filtered_count < total_rows:
            self.lbl_dims.setText(f"Filtered: {filtered_count:,} of {total_rows:,} rows")
        else:
            self.lbl_dims.setText(f"{total_rows:,} total rows × {len(self.table_model.get_dataframe().columns)} columns")

    def _on_header_clicked(self, logical_index: int):
        current_sort_col = self.table_model._sort_col
        current_order = self.table_model._sort_order
        if current_sort_col == logical_index:
            new_order = (
                Qt.SortOrder.DescendingOrder
                if current_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            new_order = Qt.SortOrder.AscendingOrder
        self.table_model.sort(logical_index, new_order)

    def _show_header_context_menu(self, pos):
        logical_index = self.table_view.horizontalHeader().logicalIndexAt(pos)
        if logical_index < 0:
            return

        df = self.table_model.get_dataframe()
        if logical_index >= len(df.columns):
            return
        col_name = str(df.columns[logical_index])

        menu = QMenu(self)

        act_filter = menu.addAction(f"🔍 Filter '{col_name}'...")
        act_filter.triggered.connect(lambda: self._open_filter_dialog_for_column(col_name))

        if col_name in self.table_model.active_filters:
            act_rm_filter = menu.addAction(f"❌ Remove Filter on '{col_name}'")
            act_rm_filter.triggered.connect(lambda: self._remove_filter(col_name))

        menu.addSeparator()

        act_sort_asc = menu.addAction("▲ Sort Ascending")
        act_sort_asc.triggered.connect(lambda: self.table_model.sort(logical_index, Qt.SortOrder.AscendingOrder))

        act_sort_desc = menu.addAction("▼ Sort Descending")
        act_sort_desc.triggered.connect(lambda: self.table_model.sort(logical_index, Qt.SortOrder.DescendingOrder))

        menu.addSeparator()

        # Column schema operations
        act_rename = menu.addAction(f"✏️ Rename Column '{col_name}'...")
        act_rename.triggered.connect(lambda: self._rename_column(col_name))

        act_delete_col = menu.addAction(f"🗑️ Delete Column '{col_name}'")
        act_delete_col.triggered.connect(lambda: self._delete_column(col_name))

        menu.addSeparator()

        act_hide_col = menu.addAction(f"👁️ Hide Column '{col_name}'")
        act_hide_col.triggered.connect(lambda: self._hide_single_column(col_name))

        act_manage_cols = menu.addAction("Manage Columns View...")
        act_manage_cols.triggered.connect(self._open_column_manager)

        menu.exec(QCursor.pos())

    def _hide_single_column(self, col_name: str):
        self._hidden_columns.add(col_name)
        self.set_hidden_columns(self._hidden_columns)

    def _open_column_manager(self):
        df = self.table_model.get_dataframe()
        if df.empty:
            QMessageBox.information(self, "Columns", "No Parquet dataset loaded.")
            return
        col_names = [str(c) for c in df.columns]
        dlg = ColumnManagerDialog(col_names, self._hidden_columns, self)
        if dlg.exec():
            self.set_hidden_columns(dlg.get_hidden_columns())

    def _on_pagination_toggled(self, enabled: bool):
        if not enabled:
            self.table_model.set_page_size(-1)
        else:
            size = self.pagination_bar.page_size
            self.table_model.set_page_size(size if size > 0 else 250)

    def _on_pagination_state_changed(self):
        filtered_count = self.table_model.get_total_filtered_rows()
        self.pagination_bar.update_pagination(filtered_count)

    def _on_model_modified(self):
        filtered_count = self.table_model.get_total_filtered_rows()
        self.pagination_bar.update_pagination(filtered_count)
        self.data_changed.emit()

    # -------------------------------------------------------------------------
    # Column Schema Operations
    # -------------------------------------------------------------------------

    def _add_column(self):
        df = self.table_model.get_dataframe()
        existing = [str(c) for c in df.columns] if not df.empty else []
        dlg = AddColumnDialog(existing, self)
        if dlg.exec():
            name, dtype_key, default = dlg.get_result()
            self.table_model.add_column(name, dtype_key, default)
            # Resize new column
            new_idx = list(self.table_model.get_dataframe().columns).index(name)
            self.table_view.setColumnWidth(new_idx, 150)
            self._on_model_modified()

    def _rename_column(self, col_name: str):
        df = self.table_model.get_dataframe()
        existing = [str(c) for c in df.columns]
        dlg = RenameColumnDialog(col_name, existing, self)
        if dlg.exec():
            new_name = dlg.get_new_name()
            if new_name and new_name != col_name:
                self.table_model.rename_column(col_name, new_name)
                self._on_model_modified()

    def _delete_column(self, col_name: str):
        reply = QMessageBox.question(
            self,
            "Delete Column",
            f"Are you sure you want to delete column '{col_name}'?\n\nThis can be undone with Ctrl+Z.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.table_model.delete_column(col_name)
            self._on_model_modified()

    def _open_formula_builder(self, existing_col: Optional[str] = None):
        df = self.table_model.get_dataframe()
        if df.empty:
            QMessageBox.information(self, "Formula Builder", "No data loaded.")
            return
        dlg = FormulaBuilderDialog(df, existing_col=existing_col, parent=self)
        if dlg.exec():
            target_col, result_series = dlg.get_result()
            if target_col is not None and result_series is not None:
                self.table_model.apply_formula(target_col, result_series)
                # Refresh column widths if new column
                if target_col not in [str(c) for c in df.columns]:
                    new_idx = len(self.table_model.get_dataframe().columns) - 1
                    self.table_view.setColumnWidth(new_idx, 160)
                self._on_model_modified()

    # -------------------------------------------------------------------------
    # Search, Row, Stats & General Helpers
    # -------------------------------------------------------------------------

    def _toggle_search_toolbar(self):
        visible = not self.search_toolbar.isVisible()
        self.search_toolbar.setVisible(visible)
        if visible:
            self.search_toolbar.focus_search()

    def _perform_search(self, text: str, case_sensitive: bool):
        self._search_matches = []
        self._search_match_idx = -1

        if not text:
            self.search_toolbar.update_match_status(-1, 0)
            return

        df = self.table_model.get_dataframe()
        if df.empty:
            return

        matches = []
        for c_idx, col in enumerate(df.columns):
            series_str = df[col].astype(str)
            if not case_sensitive:
                mask = series_str.str.lower().str.contains(text.lower(), regex=False, na=False)
            else:
                mask = series_str.str.contains(text, regex=False, na=False)
            matching_rows = np.flatnonzero(mask.values)
            for r_idx in matching_rows:
                matches.append((int(r_idx), c_idx))

        matches.sort(key=lambda item: (item[0], item[1]))
        self._search_matches = matches
        if matches:
            self._search_match_idx = 0
            self._highlight_match(0)
        else:
            self.search_toolbar.update_match_status(-1, 0)

    def _navigate_search_match(self, direction: int):
        if not self._search_matches:
            return
        self._search_match_idx = (self._search_match_idx + direction) % len(self._search_matches)
        self._highlight_match(self._search_match_idx)

    def _highlight_match(self, idx: int):
        if 0 <= idx < len(self._search_matches):
            actual_r, c = self._search_matches[idx]
            if self.table_model.page_size > 0:
                page = (actual_r // self.table_model.page_size) + 1
                visual_r = actual_r % self.table_model.page_size
                self.pagination_bar.set_page(page)
            else:
                visual_r = actual_r
            model_index = self.table_model.index(visual_r, c)
            self.table_view.setCurrentIndex(model_index)
            self.table_view.scrollTo(model_index, QAbstractItemView.ScrollHint.PositionAtCenter)
            self.search_toolbar.update_match_status(idx, len(self._search_matches))

    def _jump_to_row(self, row: int):
        if self.table_model.page_size > 0:
            page = (row // self.table_model.page_size) + 1
            visual_r = row % self.table_model.page_size
            self.pagination_bar.set_page(page)
        else:
            visual_r = row
        if 0 <= visual_r < self.table_model.rowCount():
            model_index = self.table_model.index(visual_r, 0)
            self.table_view.setCurrentIndex(model_index)
            self.table_view.scrollTo(model_index, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _add_row(self):
        self.table_model.insert_row()

    def _delete_selected_rows(self):
        selection = self.table_view.selectionModel().selectedIndexes()
        if not selection:
            QMessageBox.information(self, "Delete Rows", "Please select at least one cell in the row(s) to delete.")
            return

        rows = sorted(set(idx.row() for idx in selection))
        confirm = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete {len(rows)} row(s)?\n\nThis can be undone with Ctrl+Z.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.table_model.delete_rows(rows)

    def _show_schema_dialog(self):
        if not self._current_metadata:
            QMessageBox.information(self, "Schema", "No Parquet file loaded.")
            return
        dlg = SchemaDialog(self._current_metadata, self)
        dlg.exec()

    def _update_stats_bar(self):
        selection = self.table_view.selectionModel().selectedIndexes()
        if not selection:
            self.lbl_stats.setText("")
            return

        stats = self.table_model.compute_stats(selection)
        parts = [f"Count: {stats['count']}"]
        if stats["is_numeric"] and stats["sum"] is not None:
            parts.append(f"Sum: {stats['sum']:g}")
            parts.append(f"Average: {stats['avg']:g}")
            parts.append(f"Min: {stats['min']:g}")
            parts.append(f"Max: {stats['max']:g}")
        self.lbl_stats.setText("   |   ".join(parts))

    def open_working_copy_diff(self):
        """Opens the Git-style Diff Dialog to review unsaved changes against baseline."""
        base_df = self.table_model.get_original_dataframe()
        current_df = self.table_model.get_dataframe()
        file_name = self._current_metadata.get("file_name", "Current Parquet") if self._current_metadata else "Current Parquet"

        dlg = WorkingCopyDiffDialog(base_df, current_df, file_name=file_name, parent=self)
        dlg.revert_requested.connect(self._revert_all_to_baseline)
        dlg.exec()

    def _revert_all_to_baseline(self):
        base_df = self.table_model.get_original_dataframe()
        self.table_model.set_dataframe(base_df)
        self.table_model.mark_clean()
        self._on_model_modified()
        QMessageBox.information(self, "Reverted", "All changes have been reverted back to the original file.")

    def _show_context_menu(self, pos):
        index = self.table_view.indexAt(pos)
        menu = QMenu(self)

        act_copy = menu.addAction("📋 Copy (Ctrl+C)")
        act_copy.triggered.connect(self.table_view.copy_selection)

        act_paste = menu.addAction("📥 Paste (Ctrl+V)")
        act_paste.triggered.connect(self.table_view.paste_selection)

        menu.addSeparator()

        col_name = None
        if index.isValid():
            df = self.table_model.get_dataframe()
            col_name = str(df.columns[index.column()])
            act_col_filter = menu.addAction(f"🔍 Filter by '{col_name}'...")
            act_col_filter.triggered.connect(lambda: self._open_filter_dialog_for_column(col_name))

            act_rename = menu.addAction(f"✏️ Rename Column '{col_name}'...")
            act_rename.triggered.connect(lambda: self._rename_column(col_name))

        act_add_col = menu.addAction("➕ Add New Column...")
        act_add_col.triggered.connect(self._add_column)

        menu.addSeparator()

        act_add_row = menu.addAction("➕ Insert Row Below")
        act_add_row.triggered.connect(self._add_row)

        act_del_row = menu.addAction("🗑️ Delete Selected Row(s)")
        act_del_row.triggered.connect(self._delete_selected_rows)

        menu.addSeparator()

        act_diff = menu.addAction("🔍 Review Changes (Git Diff)...")
        act_diff.triggered.connect(self.open_working_copy_diff)

        if col_name:
            act_formula = menu.addAction(f"𝑓 Formula Builder for '{col_name}'...")
            act_formula.triggered.connect(lambda: self._open_formula_builder(existing_col=col_name))
        else:
            act_formula = menu.addAction("𝑓 Formula Builder...")
            act_formula.triggered.connect(lambda: self._open_formula_builder())

        act_cols = menu.addAction("👁️ Manage Columns View...")
        act_cols.triggered.connect(self._open_column_manager)

        act_schema = menu.addAction("📊 View Schema & Types")
        act_schema.triggered.connect(self._show_schema_dialog)

        menu.exec(QCursor.pos())
