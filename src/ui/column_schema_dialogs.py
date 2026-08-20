"""
Add / Rename Column Dialogs for Parquet Editor.
"""
from __future__ import annotations

from typing import Optional, Tuple, Any
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QDialogButtonBox, QFormLayout,
    QMessageBox, QDoubleSpinBox, QCheckBox,
)

DTYPE_OPTIONS = [
    ("string (text)",    "string"),
    ("int64 (integer)",  "int64"),
    ("float64 (decimal)","float64"),
    ("bool (true/false)","bool"),
    ("datetime64 (timestamp)", "datetime64"),
    ("date32 (date only)", "date32"),
]


class AddColumnDialog(QDialog):
    """Dialog to specify name, data type, and default value for a new column."""

    def __init__(self, existing_columns: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add New Column")
        self.setMinimumWidth(400)
        self._existing = set(existing_columns)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Column name
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("e.g.  total_price")
        form.addRow("Column Name:", self.txt_name)

        # Data type
        self.cmb_type = QComboBox()
        for label, _ in DTYPE_OPTIONS:
            self.cmb_type.addItem(label)
        form.addRow("Data Type:", self.cmb_type)

        # Default value
        self.txt_default = QLineEdit()
        self.txt_default.setPlaceholderText("Leave blank for null / empty")
        form.addRow("Default Value:", self.txt_default)

        layout.addLayout(form)

        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet("color: #e36262; font-size: 11px;")
        layout.addWidget(self.lbl_info)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self):
        name = self.txt_name.text().strip()
        if not name:
            self.lbl_info.setText("Column name cannot be empty.")
            return
        if name in self._existing:
            self.lbl_info.setText(f"Column '{name}' already exists.")
            return
        self.accept()

    def get_result(self) -> Tuple[str, str, str]:
        """Returns (name, dtype_key, default_value_string)."""
        name = self.txt_name.text().strip()
        dtype_key = DTYPE_OPTIONS[self.cmb_type.currentIndex()][1]
        default = self.txt_default.text().strip()
        return name, dtype_key, default


class RenameColumnDialog(QDialog):
    """Dialog to rename an existing column."""

    def __init__(self, current_name: str, existing_columns: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Rename Column: '{current_name}'")
        self.setMinimumWidth(360)
        self._existing = set(existing_columns) - {current_name}
        self._current = current_name

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.txt_name = QLineEdit(current_name)
        self.txt_name.selectAll()
        form.addRow("New Name:", self.txt_name)
        layout.addLayout(form)

        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet("color: #e36262; font-size: 11px;")
        layout.addWidget(self.lbl_info)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self):
        name = self.txt_name.text().strip()
        if not name:
            self.lbl_info.setText("Column name cannot be empty.")
            return
        if name in self._existing:
            self.lbl_info.setText(f"Column '{name}' already exists.")
            return
        self.accept()

    def get_new_name(self) -> str:
        return self.txt_name.text().strip()
