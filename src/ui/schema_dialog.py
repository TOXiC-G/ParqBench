"""
Schema and Metadata Inspector Dialog.
"""
from __future__ import annotations

from typing import Dict, Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QLabel,
    QPushButton,
    QTabWidget,
    QWidget,
    QHeaderView,
)


class SchemaDialog(QDialog):
    """Displays detailed column data types, null statistics, and Parquet file metadata."""

    def __init__(self, metadata: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Parquet Schema & Metadata — {metadata.get('file_name', 'File')}")
        self.resize(750, 480)
        self._metadata = metadata

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Tab widget for Columns and File Properties
        tabs = QTabWidget()

        # Tab 1: Column Schema
        col_tab = QWidget()
        col_layout = QVBoxLayout(col_tab)
        col_layout.setContentsMargins(4, 4, 4, 4)

        col_table = QTableWidget()
        col_table.setColumnCount(5)
        col_table.setHorizontalHeaderLabels([
            "Column Name",
            "PyArrow Type",
            "Pandas Dtype",
            "Nullable",
            "Null Count (%)",
        ])
        col_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        col_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        col_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        col_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        col_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        col_table.verticalHeader().setVisible(False)
        col_table.setAlternatingRowColors(True)

        columns = self._metadata.get("columns", {})
        total_rows = self._metadata.get("num_rows", 0)
        col_table.setRowCount(len(columns))

        for row, (col_name, info) in enumerate(columns.items()):
            col_table.setItem(row, 0, QTableWidgetItem(str(col_name)))
            col_table.setItem(row, 1, QTableWidgetItem(str(info.get("arrow_type", ""))))
            col_table.setItem(row, 2, QTableWidgetItem(str(info.get("pandas_dtype", ""))))
            
            nullable_str = "Yes" if info.get("nullable", True) else "No"
            col_table.setItem(row, 3, QTableWidgetItem(nullable_str))
            
            null_count = info.get("null_count", 0)
            pct = (null_count / total_rows * 100) if total_rows > 0 else 0
            null_str = f"{null_count:,} ({pct:.1f}%)"
            col_table.setItem(row, 4, QTableWidgetItem(null_str))

        col_layout.addWidget(col_table)
        tabs.addTab(col_tab, "Columns & Types")

        # Tab 2: General & Custom Metadata
        prop_tab = QWidget()
        prop_layout = QVBoxLayout(prop_tab)
        prop_layout.setContentsMargins(8, 8, 8, 8)

        prop_table = QTableWidget()
        prop_table.setColumnCount(2)
        prop_table.setHorizontalHeaderLabels(["Property", "Value"])
        prop_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        prop_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        prop_table.verticalHeader().setVisible(False)

        props = [
            ("File Path", self._metadata.get("file_path", "")),
            ("File Size", f"{self._metadata.get('file_size_bytes', 0) / 1024:.2f} KB"),
            ("Total Rows", f"{self._metadata.get('num_rows', 0):,}"),
            ("Total Columns", f"{self._metadata.get('num_cols', 0)}"),
            ("Row Groups", f"{self._metadata.get('num_row_groups', 1)}"),
        ]

        # Add custom metadata key-values
        for k, v in self._metadata.get("custom_metadata", {}).items():
            props.append((f"Metadata: {k}", str(v)))

        prop_table.setRowCount(len(props))
        for row, (k, v) in enumerate(props):
            prop_table.setItem(row, 0, QTableWidgetItem(k))
            prop_table.setItem(row, 1, QTableWidgetItem(str(v)))

        prop_layout.addWidget(prop_table)
        tabs.addTab(prop_tab, "File Properties")

        layout.addWidget(tabs, 1)

        # Bottom buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch(1)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)
