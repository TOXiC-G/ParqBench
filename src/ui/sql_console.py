"""
DuckDB SQL Query Console for Parquet Editor.
Provides an embeddable dock-style SQL editor that queries the currently-loaded
DataFrame using DuckDB, with zero-copy Arrow memory sharing where possible.
"""
from __future__ import annotations

import traceback
from typing import Optional
import pandas as pd
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QTableView, QSplitter, QComboBox, QAbstractItemView,
    QHeaderView, QSizePolicy, QFrame,
)
from PySide6.QtGui import QFont, QKeySequence, QShortcut

from src.models.parquet_table_model import ParquetTableModel


class _SqlWorker(QObject):
    """Runs DuckDB query in a background thread to avoid blocking the UI."""
    finished = Signal(object, str)   # (result_df or None, error_message)

    def __init__(self, sql: str, df: pd.DataFrame):
        super().__init__()
        self._sql = sql
        self._df = df

    def run(self):
        try:
            import duckdb
            conn = duckdb.connect()
            # Register the current DataFrame as 'current_table'
            conn.register("current_table", self._df)
            result_df = conn.execute(self._sql).df()
            conn.close()
            self.finished.emit(result_df, "")
        except Exception as ex:
            self.finished.emit(None, str(ex))


class SqlConsoleWidget(QWidget):
    """Collapsible SQL console dock that queries the loaded DataFrame with DuckDB."""

    run_query_requested = Signal(str)  # emitted with the SQL text

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: Optional[pd.DataFrame] = None
        self._worker: Optional[_SqlWorker] = None
        self._thread: Optional[QThread] = None

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QFrame()
        header.setStyleSheet("background: #18181f; border-bottom: 1px solid #2d2d3a;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 6, 10, 6)

        lbl = QLabel("🦆 DuckDB SQL Console")
        lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #c0d0ff;")
        header_layout.addWidget(lbl)

        self.lbl_status = QLabel("Ready — type SQL below. Table name: current_table")
        self.lbl_status.setStyleSheet("color: #778899; font-size: 11px;")
        header_layout.addWidget(self.lbl_status, 1)

        self.btn_run = QPushButton("▶ Run (Ctrl+Enter)")
        self.btn_run.setStyleSheet(
            "background: #107c41; color: white; border-radius: 4px; padding: 4px 14px; font-weight: bold;"
        )
        self.btn_run.clicked.connect(self._run_query)
        header_layout.addWidget(self.btn_run)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self._clear_editor)
        header_layout.addWidget(self.btn_clear)

        layout.addWidget(header)

        # Splitter: editor top, results bottom
        splitter = QSplitter(Qt.Orientation.Vertical)

        # SQL Editor
        self.txt_sql = QTextEdit()
        self.txt_sql.setPlaceholderText(
            "-- Query the loaded Parquet file\n"
            "SELECT * FROM current_table LIMIT 100;\n\n"
            "-- Aggregate example\n"
            "SELECT category, COUNT(*) AS cnt, AVG(price) AS avg_price\n"
            "FROM current_table\n"
            "GROUP BY category\n"
            "ORDER BY cnt DESC;"
        )
        mono = QFont("Consolas", 11)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.txt_sql.setFont(mono)
        self.txt_sql.setMinimumHeight(80)
        self.txt_sql.setMaximumHeight(180)
        self.txt_sql.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        splitter.addWidget(self.txt_sql)

        # Results table
        result_frame = QFrame()
        res_layout = QVBoxLayout(result_frame)
        res_layout.setContentsMargins(0, 0, 0, 0)
        res_layout.setSpacing(0)

        self.lbl_result_info = QLabel("")
        self.lbl_result_info.setStyleSheet("padding: 4px 10px; color: #70b8ff; font-size: 11px;")
        res_layout.addWidget(self.lbl_result_info)

        self.result_model = ParquetTableModel(parent=self)
        self.result_view = QTableView()
        self.result_view.setModel(self.result_model)
        self.result_view.setAlternatingRowColors(True)
        self.result_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.result_view.horizontalHeader().setStretchLastSection(True)
        self.result_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.result_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        res_layout.addWidget(self.result_view)
        splitter.addWidget(result_frame)

        splitter.setSizes([140, 260])
        layout.addWidget(splitter, 1)

        # Ctrl+Enter shortcut
        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.txt_sql)
        shortcut.activated.connect(self._run_query)

    def set_dataframe(self, df: Optional[pd.DataFrame]):
        """Call whenever the active file changes."""
        self._df = df
        if df is not None:
            self.lbl_status.setText(
                f"Ready — {len(df):,} rows × {len(df.columns)} cols | Table: current_table"
            )
        else:
            self.lbl_status.setText("No file loaded.")

    def _run_query(self):
        if self._df is None or self._df.empty:
            self.lbl_status.setText("⚠️ No data loaded. Open a Parquet file first.")
            return

        sql = self.txt_sql.toPlainText().strip()
        if not sql:
            return

        self.btn_run.setEnabled(False)
        self.lbl_status.setText("⏳ Running query…")

        self._thread = QThread()
        self._worker = _SqlWorker(sql, self._df)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_query_done)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _on_query_done(self, result_df: Optional[pd.DataFrame], error: str):
        self.btn_run.setEnabled(True)
        if error:
            self.lbl_status.setText(f"❌ {error}")
            self.lbl_result_info.setText("")
            return

        if result_df is not None and not result_df.empty:
            self.result_model.set_dataframe(result_df)
            # Resize columns to content
            self.result_view.resizeColumnsToContents()
            rows, cols = len(result_df), len(result_df.columns)
            self.lbl_status.setText(f"✅ Query returned {rows:,} rows × {cols} columns")
            self.lbl_result_info.setText(
                f"Result: {rows:,} rows × {cols} columns"
            )
        else:
            self.result_model.set_dataframe(pd.DataFrame())
            self.lbl_status.setText("✅ Query executed (no rows returned)")
            self.lbl_result_info.setText("No rows returned.")

    def _clear_editor(self):
        self.txt_sql.clear()
        self.result_model.set_dataframe(pd.DataFrame())
        self.lbl_result_info.setText("")
