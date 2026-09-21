"""
Main Application Window for Parquet Editor — v2.
Multi-tab workspace, Undo/Redo, Column Schema ops, DuckDB SQL Console,
Data Profiler, Parquet Diff, Hive Partition loader.
"""
from __future__ import annotations

import os
from typing import Optional, List
import pyarrow as pa
import pyarrow.dataset as pad

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QFileDialog,
    QMessageBox,
    QLabel,
    QStatusBar,
    QToolBar,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QDockWidget,
)
from PySide6.QtGui import QAction, QKeySequence, QUndoGroup

from src.engine.parquet_handler import ParquetHandler
from src.ui.file_explorer import FileExplorerWidget
from src.ui.data_grid_view import DataGridWidget
from src.ui.sql_console import SqlConsoleWidget
from src.ui.data_profiler import DataProfilerWidget
from src.ui.parquet_diff import ParquetDiffDialog, WorkingCopyDiffDialog
from src.ui.column_schema_dialogs import AddColumnDialog
from src.ui.styles import MODERN_DARK_THEME, MODERN_LIGHT_THEME


class TabEntry:
    """Metadata for each open tab."""
    def __init__(self, grid: DataGridWidget, file_path: Optional[str], schema: Optional[pa.Schema]):
        self.grid = grid
        self.file_path = file_path
        self.schema = schema


class MainWindow(QMainWindow):
    """Main window with multi-tab split-pane layout and non-destructive Parquet file editing."""

    def __init__(self, initial_file: Optional[str] = None):
        super().__init__()
        self.setWindowTitle("Parquet Editor — Excel-like Tabular Suite")
        self.resize(1380, 820)
        self.setMinimumSize(900, 550)

        self._is_dark_theme = True
        # UndoGroup tracks the active tab's undo stack
        self._undo_group = QUndoGroup(self)
        self._tabs: List[TabEntry] = []

        self._setup_ui()
        self._setup_menus_and_toolbars()
        self._apply_theme()

        if initial_file and os.path.exists(initial_file):
            self.open_file_in_new_tab(initial_file)
        else:
            # Start with one blank tab
            self._new_tab()

    # =========================================================================
    # UI Setup
    # =========================================================================

    def _setup_ui(self):
        # Root horizontal splitter: [left explorer] | [center tabs + bottom docks]
        self.root_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.root_splitter.setChildrenCollapsible(False)

        # Left Pane: File Explorer
        self.file_explorer = FileExplorerWidget(os.getcwd(), self)
        self.file_explorer.file_selected.connect(self._on_file_selected)
        self.root_splitter.addWidget(self.file_explorer)

        # Center: vertical splitter [tab area] / [SQL console]
        self.center_splitter = QSplitter(Qt.Orientation.Vertical)

        # Tab Widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.center_splitter.addWidget(self.tab_widget)

        # SQL Console (collapsible dock-style at bottom)
        self.sql_console = SqlConsoleWidget(self)
        self.sql_console.setVisible(False)
        self.center_splitter.addWidget(self.sql_console)
        self.center_splitter.setSizes([600, 300])

        self.root_splitter.addWidget(self.center_splitter)

        # Right Dock: Data Profiler
        self.profiler = DataProfilerWidget(self)
        profiler_dock = QDockWidget("Data Profiler", self)
        profiler_dock.setWidget(self.profiler)
        profiler_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        profiler_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, profiler_dock)
        self._profiler_dock = profiler_dock
        profiler_dock.hide()

        self.root_splitter.setSizes([260, 1100])
        self.setCentralWidget(self.root_splitter)

        # Status Bar
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.lbl_status_msg = QLabel("Ready")
        self.lbl_status_file = QLabel("No active file")
        self.lbl_status_file.setStyleSheet("color: #70a0ff; font-weight: 500;")
        self.status_bar.addWidget(self.lbl_status_msg, 1)
        self.status_bar.addPermanentWidget(self.lbl_status_file)

    # =========================================================================
    # Menus & Toolbars
    # =========================================================================

    def _setup_menus_and_toolbars(self):
        menubar = self.menuBar()

        # ----- FILE MENU -----
        file_menu = menubar.addMenu("&File")

        act_open_file = QAction("📂 Open Parquet File...", self)
        act_open_file.setShortcut(QKeySequence.StandardKey.Open)
        act_open_file.triggered.connect(self._open_file_dialog)
        file_menu.addAction(act_open_file)

        act_open_folder = QAction("📁 Open Folder...", self)
        act_open_folder.triggered.connect(self._open_folder_dialog)
        file_menu.addAction(act_open_folder)

        act_open_partition = QAction("🗂️ Open Partitioned Directory (Hive)...", self)
        act_open_partition.triggered.connect(self._open_partitioned_dir)
        file_menu.addAction(act_open_partition)

        file_menu.addSeparator()

        act_new_tab = QAction("➕ New Tab", self)
        act_new_tab.setShortcut(QKeySequence("Ctrl+T"))
        act_new_tab.triggered.connect(self._new_tab)
        file_menu.addAction(act_new_tab)

        act_close_tab = QAction("✕ Close Tab", self)
        act_close_tab.setShortcut(QKeySequence("Ctrl+W"))
        act_close_tab.triggered.connect(lambda: self._close_tab(self.tab_widget.currentIndex()))
        file_menu.addAction(act_close_tab)

        file_menu.addSeparator()

        self.act_save = QAction("💾 Save (Non-Destructive)...", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.setToolTip("Forces a Save As dialog to protect the original file")
        self.act_save.triggered.connect(self._save_file_non_destructive)
        file_menu.addAction(self.act_save)

        act_save_as = QAction("💾 Save As...", self)
        act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        act_save_as.triggered.connect(self._save_file_as)
        file_menu.addAction(act_save_as)

        file_menu.addSeparator()

        export_menu = file_menu.addMenu("📤 Export")
        export_menu.addAction("Export to CSV (.csv)...").triggered.connect(self._export_csv)
        export_menu.addAction("Export to Excel (.xlsx)...").triggered.connect(self._export_excel)
        export_menu.addAction("Export to JSON (.json)...").triggered.connect(self._export_json)

        file_menu.addSeparator()

        act_exit = QAction("❌ Exit", self)
        act_exit.setShortcut(QKeySequence("Ctrl+Q"))
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # ----- EDIT MENU -----
        edit_menu = menubar.addMenu("&Edit")

        # Undo / Redo wired to UndoGroup
        self.act_undo = self._undo_group.createUndoAction(self, "↩ Undo")
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(self.act_undo)

        self.act_redo = self._undo_group.createRedoAction(self, "↪ Redo")
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(self.act_redo)

        edit_menu.addSeparator()

        act_copy = QAction("📋 Copy", self)
        act_copy.setShortcut(QKeySequence.StandardKey.Copy)
        act_copy.triggered.connect(self._copy_active)
        edit_menu.addAction(act_copy)

        act_paste = QAction("📥 Paste", self)
        act_paste.setShortcut(QKeySequence.StandardKey.Paste)
        act_paste.triggered.connect(self._paste_active)
        edit_menu.addAction(act_paste)

        act_clear = QAction("🧹 Clear Cells", self)
        act_clear.setShortcut(QKeySequence.StandardKey.Delete)
        act_clear.triggered.connect(self._clear_active)
        edit_menu.addAction(act_clear)

        edit_menu.addSeparator()

        act_find = QAction("🔍 Find...", self)
        act_find.setShortcut(QKeySequence.StandardKey.Find)
        act_find.triggered.connect(self._find_active)
        edit_menu.addAction(act_find)

        edit_menu.addSeparator()

        act_add_row = QAction("➕ Add Row", self)
        act_add_row.triggered.connect(self._add_row_active)
        edit_menu.addAction(act_add_row)

        act_del_row = QAction("🗑️ Delete Selected Row(s)", self)
        act_del_row.triggered.connect(self._del_row_active)
        edit_menu.addAction(act_del_row)

        edit_menu.addSeparator()

        act_add_col = QAction("➕ Add Column...", self)
        act_add_col.triggered.connect(self._add_column_active)
        edit_menu.addAction(act_add_col)

        act_formula = QAction("𝑓 Formula Builder...", self)
        act_formula.triggered.connect(self._formula_active)
        edit_menu.addAction(act_formula)

        edit_menu.addSeparator()

        self.act_review_changes = QAction("🔍 Review Changes / Diff with Original...", self)
        self.act_review_changes.setShortcut(QKeySequence("Ctrl+Shift+D"))
        self.act_review_changes.setToolTip("Open Git-style diff inspector for unsaved changes (Ctrl+Shift+D)")
        self.act_review_changes.triggered.connect(self._review_changes_active)
        edit_menu.addAction(self.act_review_changes)

        # ----- VIEW MENU -----
        view_menu = menubar.addMenu("&View")

        self.act_toggle_explorer = QAction("Toggle File Explorer", self)
        self.act_toggle_explorer.setCheckable(True)
        self.act_toggle_explorer.setChecked(True)
        self.act_toggle_explorer.triggered.connect(self._toggle_file_explorer)
        view_menu.addAction(self.act_toggle_explorer)

        self.act_toggle_sql = QAction("🦆 Toggle SQL Console", self)
        self.act_toggle_sql.setCheckable(True)
        self.act_toggle_sql.setChecked(False)
        self.act_toggle_sql.setShortcut(QKeySequence("Ctrl+Shift+Q"))
        self.act_toggle_sql.triggered.connect(self._toggle_sql_console)
        view_menu.addAction(self.act_toggle_sql)

        self.act_toggle_profiler = QAction("📊 Toggle Data Profiler", self)
        self.act_toggle_profiler.setCheckable(True)
        self.act_toggle_profiler.setChecked(False)
        self.act_toggle_profiler.setShortcut(QKeySequence("Ctrl+Shift+P"))
        self.act_toggle_profiler.triggered.connect(self._toggle_profiler)
        view_menu.addAction(self.act_toggle_profiler)

        view_menu.addSeparator()

        act_cols = QAction("👁️ Manage Column Visibility...", self)
        act_cols.triggered.connect(self._col_visibility_active)
        view_menu.addAction(act_cols)

        act_clear_filters = QAction("🧹 Clear All Active Filters", self)
        act_clear_filters.triggered.connect(self._clear_filters_active)
        view_menu.addAction(act_clear_filters)

        view_menu.addSeparator()

        act_schema = QAction("📐 Schema & Data Types...", self)
        act_schema.triggered.connect(self._schema_active)
        view_menu.addAction(act_schema)

        view_menu.addSeparator()

        act_toggle_theme = QAction("🌗 Toggle Dark / Light Theme", self)
        act_toggle_theme.triggered.connect(self._toggle_theme)
        view_menu.addAction(act_toggle_theme)

        # ----- TOOLS MENU -----
        tools_menu = menubar.addMenu("&Tools")

        act_diff = QAction("🔀 Compare Parquet Files (Diff)...", self)
        act_diff.triggered.connect(self._open_diff_tool)
        tools_menu.addAction(act_diff)

        # ----- HELP MENU -----
        help_menu = menubar.addMenu("&Help")
        act_about = QAction("ℹ️ About Parquet Editor", self)
        act_about.triggered.connect(self._show_about_dialog)
        help_menu.addAction(act_about)

        # ----- TOOLBAR -----
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addAction(act_open_file)
        toolbar.addAction(act_open_folder)
        toolbar.addSeparator()
        toolbar.addAction(self.act_save)
        toolbar.addSeparator()
        toolbar.addAction(self.act_undo)
        toolbar.addAction(self.act_redo)
        toolbar.addSeparator()
        toolbar.addAction(act_copy)
        toolbar.addAction(act_paste)
        toolbar.addAction(act_find)
        toolbar.addSeparator()
        toolbar.addAction(act_add_col)
        toolbar.addAction(act_formula)
        toolbar.addSeparator()
        toolbar.addAction(self.act_toggle_sql)
        toolbar.addAction(self.act_toggle_profiler)
        toolbar.addAction(act_diff)
        toolbar.addAction(self.act_review_changes)

    # =========================================================================
    # Tab Management
    # =========================================================================

    def _new_tab(self, title: str = "Untitled") -> DataGridWidget:
        grid = DataGridWidget(self)
        grid.data_changed.connect(self._on_data_modified)

        # Register this tab's undo stack with the group
        self._undo_group.addStack(grid.undo_stack)

        entry = TabEntry(grid=grid, file_path=None, schema=None)
        self._tabs.append(entry)

        idx = self.tab_widget.addTab(grid, title)
        self.tab_widget.setCurrentIndex(idx)
        return grid

    def _close_tab(self, index: int):
        if self.tab_widget.count() <= 1:
            # Don't close the last tab; just clear it
            self._new_tab()
            self.tab_widget.removeTab(0)
            if self._tabs:
                self._tabs.pop(0)
            return

        if 0 <= index < len(self._tabs):
            entry = self._tabs[index]
            if entry.grid.is_dirty:
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "This tab has unsaved changes. Discard and close?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Cancel:
                    return
            self._undo_group.removeStack(entry.grid.undo_stack)
            self._tabs.pop(index)

        self.tab_widget.removeTab(index)

    def _on_tab_changed(self, index: int):
        if 0 <= index < len(self._tabs):
            entry = self._tabs[index]
            # Activate this tab's undo stack
            self._undo_group.setActiveStack(entry.grid.undo_stack)

            # Update SQL console and profiler data
            if entry.grid.is_dirty or True:  # Always update
                df = entry.grid.get_dataframe()
                self.sql_console.set_dataframe(df if not df.empty else None)
                self.profiler.set_dataframe(df if not df.empty else None)

            # Update status bar
            fp = entry.file_path
            if fp:
                self.lbl_status_file.setText(f"📄 {os.path.basename(fp)} [Original Protected]")
                self.setWindowTitle(f"Parquet Editor — {os.path.basename(fp)}")
            else:
                self.lbl_status_file.setText("No active file")
                self.setWindowTitle("Parquet Editor — Untitled")

    def _current_grid(self) -> Optional[DataGridWidget]:
        idx = self.tab_widget.currentIndex()
        if 0 <= idx < len(self._tabs):
            return self._tabs[idx].grid
        return None

    def _current_entry(self) -> Optional[TabEntry]:
        idx = self.tab_widget.currentIndex()
        if 0 <= idx < len(self._tabs):
            return self._tabs[idx]
        return None

    # =========================================================================
    # File Loading
    # =========================================================================

    def open_file_in_new_tab(self, file_path: str):
        """Open a parquet file in a new tab."""
        if not os.path.exists(file_path):
            QMessageBox.critical(self, "Error", f"File does not exist: {file_path}")
            return
        try:
            self.lbl_status_msg.setText(f"Loading {os.path.basename(file_path)}...")
            df, schema, metadata = ParquetHandler.read_parquet(file_path)

            tab_title = os.path.basename(file_path)
            grid = self._new_tab(tab_title)

            # Update the TabEntry
            entry = self._tabs[-1]
            entry.file_path = file_path
            entry.schema = schema

            grid.load_data(df, metadata)

            self.lbl_status_msg.setText(f"Loaded {metadata['num_rows']:,} rows")
            self.lbl_status_file.setText(f"📄 {os.path.basename(file_path)} [Original Protected]")
            self.setWindowTitle(f"Parquet Editor — {os.path.basename(file_path)}")

            # Feed SQL console and profiler
            self.sql_console.set_dataframe(df)
            self.profiler.set_dataframe(df)

        except Exception as e:
            QMessageBox.critical(self, "Error Loading Parquet File", f"Failed to load file:\n{str(e)}")
            self.lbl_status_msg.setText("Error loading file")

    def load_file(self, file_path: str):
        """For backward compatibility: load into current tab or new tab."""
        # Check if file is already open in a tab
        for i, entry in enumerate(self._tabs):
            if entry.file_path and os.path.abspath(entry.file_path) == os.path.abspath(file_path):
                self.tab_widget.setCurrentIndex(i)
                return

        entry = self._current_entry()
        # If current tab is empty/untitled, reuse it
        if entry and entry.file_path is None and not entry.grid.is_dirty:
            if not os.path.exists(file_path):
                QMessageBox.critical(self, "Error", f"File does not exist: {file_path}")
                return
            try:
                self.lbl_status_msg.setText(f"Loading {os.path.basename(file_path)}...")
                df, schema, metadata = ParquetHandler.read_parquet(file_path)
                entry.file_path = file_path
                entry.schema = schema
                entry.grid.load_data(df, metadata)
                self.tab_widget.setTabText(self.tab_widget.currentIndex(), os.path.basename(file_path))
                self.lbl_status_msg.setText(f"Loaded {metadata['num_rows']:,} rows")
                self.lbl_status_file.setText(f"📄 {os.path.basename(file_path)} [Original Protected]")
                self.setWindowTitle(f"Parquet Editor — {os.path.basename(file_path)}")
                self.sql_console.set_dataframe(df)
                self.profiler.set_dataframe(df)
            except Exception as e:
                QMessageBox.critical(self, "Error Loading Parquet File", f"Failed to load file:\n{str(e)}")
        else:
            self.open_file_in_new_tab(file_path)

    def _open_partitioned_dir(self):
        """Load a Hive-partitioned Parquet directory as a single unified DataFrame."""
        folder = QFileDialog.getExistingDirectory(self, "Select Partitioned Parquet Directory", os.getcwd())
        if not folder:
            return
        try:
            self.lbl_status_msg.setText(f"Scanning partition directory: {os.path.basename(folder)}...")
            dataset = pad.dataset(folder, format="parquet", partitioning="hive")
            table = dataset.to_table()
            df = table.to_pandas()
            schema = table.schema

            metadata = {
                "file_path": folder,
                "file_name": f"[Partitioned] {os.path.basename(folder)}",
                "num_rows": len(df),
                "num_cols": len(df.columns),
                "file_size_bytes": 0,
                "num_row_groups": len(list(dataset.get_fragments())),
                "columns": {
                    c: {
                        "arrow_type": str(schema.field(c).type) if c in schema.names else str(df[c].dtype),
                        "pandas_dtype": str(df[c].dtype),
                        "nullable": True,
                        "null_count": int(df[c].isna().sum()),
                    }
                    for c in df.columns
                },
                "custom_metadata": {},
            }

            tab_title = f"🗂 {os.path.basename(folder)}"
            grid = self._new_tab(tab_title)
            entry = self._tabs[-1]
            entry.file_path = folder  # directory path
            entry.schema = schema
            grid.load_data(df, metadata)

            self.lbl_status_msg.setText(
                f"Loaded partitioned dataset: {len(df):,} rows × {len(df.columns)} columns"
            )
            self.sql_console.set_dataframe(df)
            self.profiler.set_dataframe(df)
        except Exception as e:
            QMessageBox.critical(self, "Partition Load Error", f"Failed to read partitioned directory:\n{str(e)}")

    # =========================================================================
    # Action Delegates (route to current grid)
    # =========================================================================

    def _copy_active(self):
        g = self._current_grid()
        if g:
            g.table_view.copy_selection()

    def _paste_active(self):
        g = self._current_grid()
        if g:
            g.table_view.paste_selection()

    def _clear_active(self):
        g = self._current_grid()
        if g:
            g.table_view.clear_selection()

    def _find_active(self):
        g = self._current_grid()
        if g:
            g.open_find()

    def _add_row_active(self):
        g = self._current_grid()
        if g:
            g._add_row()

    def _del_row_active(self):
        g = self._current_grid()
        if g:
            g._delete_selected_rows()

    def _add_column_active(self):
        g = self._current_grid()
        if g:
            g._add_column()

    def _formula_active(self):
        g = self._current_grid()
        if g:
            g._open_formula_builder()

    def _col_visibility_active(self):
        g = self._current_grid()
        if g:
            g._open_column_manager()

    def _clear_filters_active(self):
        g = self._current_grid()
        if g:
            g._clear_all_filters()

    def _schema_active(self):
        g = self._current_grid()
        if g:
            g._show_schema_dialog()

    def _review_changes_active(self):
        """Open the Git-style Working Copy Diff inspector for the active tab."""
        g = self._current_grid()
        if not g:
            return
        if not g.is_dirty:
            QMessageBox.information(
                self,
                "No Changes",
                "The current file has no unsaved changes to review.",
            )
            return
        g.open_working_copy_diff()

    # =========================================================================
    # Panel Toggles
    # =========================================================================

    def _toggle_sql_console(self, checked: bool):
        self.sql_console.setVisible(checked)
        if checked:
            g = self._current_grid()
            if g:
                df = g.get_dataframe()
                self.sql_console.set_dataframe(df if not df.empty else None)

    def _toggle_profiler(self, checked: bool):
        self._profiler_dock.setVisible(checked)
        if checked:
            g = self._current_grid()
            if g:
                df = g.get_dataframe()
                self.profiler.set_dataframe(df if not df.empty else None)

    def _open_diff_tool(self):
        entry = self._current_entry()
        current_df = entry.grid.get_dataframe() if entry else None
        current_file = entry.file_path if entry else None
        dlg = ParquetDiffDialog(current_df=current_df, current_file=current_file, parent=self)
        dlg.exec()

    # =========================================================================
    # Save & Export
    # =========================================================================

    def _save_file_non_destructive(self) -> bool:
        entry = self._current_entry()
        if not entry:
            return False

        if entry.file_path is None:
            default_dir = os.getcwd()
            suggested_name = "dataset_edited.parquet"
        else:
            folder, original_name = os.path.split(entry.file_path)
            base, ext = os.path.splitext(original_name)
            suggested_name = f"{base}_edited.parquet"
            default_dir = folder

        suggested_path = os.path.join(default_dir, suggested_name)
        dest_path, _ = QFileDialog.getSaveFileName(
            self,
            "Non-Destructive Save (Select New Parquet File Destination)",
            suggested_path,
            "Parquet Files (*.parquet);;All Files (*)",
        )

        if not dest_path:
            return False
        if not dest_path.lower().endswith(".parquet"):
            dest_path += ".parquet"

        if entry.file_path and os.path.abspath(dest_path) == os.path.abspath(entry.file_path):
            confirm = QMessageBox.warning(
                self,
                "Overwriting Original File",
                "You selected the original source file. Overwriting it will replace the original data.\nDo you still want to proceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return False

        return self._execute_save(entry, dest_path)

    def _save_file_as(self) -> bool:
        return self._save_file_non_destructive()

    def _execute_save(self, entry: TabEntry, dest_path: str) -> bool:
        df = entry.grid.get_dataframe()
        if df is None or (df.empty and entry.schema is None):
            QMessageBox.warning(self, "Save Warning", "No data to save.")
            return False
        try:
            ParquetHandler.write_parquet(df, dest_path, entry.schema)
            entry.grid.mark_saved()
            self.lbl_status_msg.setText(f"Saved to: {os.path.basename(dest_path)}")
            QMessageBox.information(
                self,
                "Save Successful",
                f"Data saved to:\n{dest_path}\n\nOriginal file untouched.",
            )
            return True
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save:\n{str(e)}")
            return False

    def _export_with_handler(self, method_name: str, dialog_title: str, file_filter: str, ext: str):
        entry = self._current_entry()
        if not entry:
            return
        df = entry.grid.get_dataframe()
        if df is None or df.empty:
            QMessageBox.information(self, "Export", "No data to export.")
            return
        dest, _ = QFileDialog.getSaveFileName(self, dialog_title, os.getcwd(), file_filter)
        if dest:
            if not dest.lower().endswith(ext):
                dest += ext
            getattr(ParquetHandler, method_name)(df, dest)
            QMessageBox.information(self, "Export Complete", f"Exported to:\n{dest}")

    def _export_csv(self):
        self._export_with_handler("export_csv", "Export to CSV", "CSV Files (*.csv)", ".csv")

    def _export_excel(self):
        self._export_with_handler("export_excel", "Export to Excel", "Excel Files (*.xlsx)", ".xlsx")

    def _export_json(self):
        self._export_with_handler("export_json", "Export to JSON", "JSON Files (*.json)", ".json")

    # =========================================================================
    # File / Folder Dialogs
    # =========================================================================

    def _on_file_selected(self, file_path: str):
        self.load_file(file_path)

    def _on_data_modified(self):
        idx = self.tab_widget.currentIndex()
        current_text = self.tab_widget.tabText(idx)
        if not current_text.endswith(" *"):
            self.tab_widget.setTabText(idx, current_text + " *")
        self.lbl_status_msg.setText("Unsaved changes")
        # Keep SQL console in sync
        g = self._current_grid()
        if g and self.sql_console.isVisible():
            self.sql_console.set_dataframe(g.get_dataframe())

    def _open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Parquet File", os.getcwd(), "Parquet Files (*.parquet);;All Files (*)"
        )
        if file_path:
            self.load_file(file_path)

    def _open_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Open Directory", os.getcwd())
        if folder:
            self.file_explorer.set_directory(folder)

    # =========================================================================
    # Theme & About
    # =========================================================================

    def _toggle_file_explorer(self, checked: bool):
        self.file_explorer.setVisible(checked)

    def _toggle_theme(self):
        self._is_dark_theme = not self._is_dark_theme
        self._apply_theme()

    def _apply_theme(self):
        self.setStyleSheet(MODERN_DARK_THEME if self._is_dark_theme else MODERN_LIGHT_THEME)

    def _show_about_dialog(self):
        QMessageBox.about(
            self,
            "About Parquet Editor",
            "<h3>Parquet Editor v2</h3>"
            "<p>A lightweight Excel-like desktop editor for Apache Parquet files.</p>"
            "<ul>"
            "<li><b>Multi-Tab Workspace</b>: Open multiple files simultaneously.</li>"
            "<li><b>Undo/Redo</b>: Full command history (Ctrl+Z / Ctrl+Y) for every edit.</li>"
            "<li><b>Column Schema Ops</b>: Add, Rename, Delete columns with undo support.</li>"
            "<li><b>Formula Builder</b>: Compute columns with pandas/numpy expressions.</li>"
            "<li><b>Spark/Excel Filtering</b>: Categorical checkboxes + numeric conditions.</li>"
            "<li><b>DuckDB SQL Console</b>: Query your loaded data with SQL.</li>"
            "<li><b>Data Profiler</b>: Per-column statistics and distribution charts.</li>"
            "<li><b>Parquet Diff</b>: Visual comparison of two Parquet files.</li>"
            "<li><b>Hive Partitions</b>: Load partitioned directories as unified datasets.</li>"
            "<li><b>Engine</b>: PySide6 (Qt6) + PyArrow + Pandas + DuckDB.</li>"
            "</ul>",
        )

    # =========================================================================
    # Close Event
    # =========================================================================

    def closeEvent(self, event):
        dirty_tabs = [e for e in self._tabs if e.grid.is_dirty]
        if dirty_tabs:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"You have unsaved changes in {len(dirty_tabs)} tab(s). Discard and exit?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        event.accept()
