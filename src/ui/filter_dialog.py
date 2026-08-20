"""
Column Filter Dialog (Spark / Excel style).
Supports value checkbox selection (categorical/text) and condition-based filtering (numeric/date).
"""
from __future__ import annotations

from typing import Any, List, Set, Dict, Optional
import pandas as pd
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QComboBox,
    QStackedWidget,
    QWidget,
    QRadioButton,
    QButtonGroup,
    QGroupBox,
    QMessageBox,
)


class ColumnFilterDialog(QDialog):
    """Excel/Spark style column filter dialog."""

    def __init__(
        self,
        col_name: str,
        series: pd.Series,
        current_filter: Optional[Dict[str, Any]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.col_name = col_name
        self.series = series
        self.current_filter = current_filter or {}
        self.is_numeric = pd.api.types.is_numeric_dtype(series.dtype) and not pd.api.types.is_bool_dtype(series.dtype)
        self.is_datetime = pd.api.types.is_datetime64_any_dtype(series.dtype)

        self.setWindowTitle(f"Filter Column: {col_name}")
        self.resize(380, 480)
        self._filter_result: Optional[Dict[str, Any]] = None

        self._setup_ui()
        self._load_current_filter()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header info
        lbl_info = QLabel(f"<b>Column:</b> {self.col_name} <span style='color: #8888aa;'>({self.series.dtype})</span>")
        layout.addWidget(lbl_info)

        # Mode selector if numeric or datetime (Values vs Conditions)
        if self.is_numeric or self.is_datetime:
            mode_box = QHBoxLayout()
            self.radio_values = QRadioButton("Values List")
            self.radio_condition = QRadioButton("Condition Filter (>, <, =, Between)")
            
            btn_group = QButtonGroup(self)
            btn_group.addButton(self.radio_values)
            btn_group.addButton(self.radio_condition)
            
            mode_box.addWidget(self.radio_values)
            mode_box.addWidget(self.radio_condition)
            layout.addLayout(mode_box)

            self.stacked_widget = QStackedWidget()
            layout.addWidget(self.stacked_widget, 1)

            # Page 0: Values list
            page_values = self._create_values_page()
            self.stacked_widget.addWidget(page_values)

            # Page 1: Condition filter
            page_condition = self._create_condition_page()
            self.stacked_widget.addWidget(page_condition)

            self.radio_values.toggled.connect(lambda checked: self.stacked_widget.setCurrentIndex(0 if checked else 1))
            self.radio_condition.setChecked(True)  # Default to conditions for numeric
        else:
            # Text / Categorical / Boolean: Only Values List
            page_values = self._create_values_page()
            layout.addWidget(page_values, 1)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        self.btn_clear = QPushButton("Clear Filter")
        self.btn_clear.clicked.connect(self._on_clear_filter)
        btn_layout.addWidget(self.btn_clear)

        btn_layout.addStretch(1)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_apply = QPushButton("Apply Filter")
        self.btn_apply.setObjectName("primaryButton")
        self.btn_apply.clicked.connect(self._on_apply)
        btn_layout.addWidget(self.btn_apply)

        layout.addLayout(btn_layout)

    def _create_values_page(self) -> QWidget:
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(6)

        # Search box for unique values
        self.txt_val_search = QLineEdit()
        self.txt_val_search.setPlaceholderText("Search values...")
        self.txt_val_search.textChanged.connect(self._filter_list_items)
        vbox.addWidget(self.txt_val_search)

        # Select All / Clear All buttons
        btn_row = QHBoxLayout()
        btn_sel_all = QPushButton("Select All")
        btn_sel_all.clicked.connect(self._select_all_values)
        btn_desel_all = QPushButton("Deselect All")
        btn_desel_all.clicked.connect(self._deselect_all_values)
        btn_row.addWidget(btn_sel_all)
        btn_row.addWidget(btn_desel_all)
        btn_row.addStretch(1)
        vbox.addLayout(btn_row)

        # List Widget with Checkboxes
        self.list_widget = QListWidget()
        self._populate_unique_values()
        vbox.addWidget(self.list_widget, 1)

        return widget

    def _create_condition_page(self) -> QWidget:
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(10)

        lbl_cond = QLabel("Filter rows where value meets condition:")
        vbox.addWidget(lbl_cond)

        self.combo_op = QComboBox()
        self.combo_op.addItems([
            "Equals (=)",
            "Does Not Equal (!=)",
            "Greater Than (>)",
            "Greater Than or Equal (>=)",
            "Less Than (<)",
            "Less Than or Equal (<=)",
            "Between (Min and Max)",
            "Is Null / Empty",
            "Is Not Null",
        ])
        self.combo_op.currentIndexChanged.connect(self._on_op_changed)
        vbox.addWidget(self.combo_op)

        self.txt_val1 = QLineEdit()
        self.txt_val1.setPlaceholderText("Value...")
        vbox.addWidget(self.txt_val1)

        self.txt_val2 = QLineEdit()
        self.txt_val2.setPlaceholderText("Maximum Value (for Between)...")
        self.txt_val2.setVisible(False)
        vbox.addWidget(self.txt_val2)

        vbox.addStretch(1)
        return widget

    def _populate_unique_values(self):
        # Extract unique values up to 5,000 distinct items
        unique_vals = self.series.dropna().unique()
        has_nulls = self.series.isna().any()

        # Sort values
        try:
            sorted_vals = sorted(unique_vals)
        except Exception:
            sorted_vals = sorted(unique_vals, key=lambda x: str(x))

        for val in sorted_vals[:5000]:
            val_str = str(val)
            item = QListWidgetItem(val_str)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, val)
            self.list_widget.addItem(item)

        if has_nulls:
            null_item = QListWidgetItem("(Null / Empty)")
            null_item.setFlags(null_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            null_item.setCheckState(Qt.CheckState.Checked)
            null_item.setData(Qt.ItemDataRole.UserRole, None)
            null_item.setForeground(Qt.GlobalColor.gray)
            self.list_widget.addItem(null_item)

    def _filter_list_items(self, text: str):
        query = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(query not in item.text().lower())

    def _select_all_values(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if not item.isHidden():
                item.setCheckState(Qt.CheckState.Checked)

    def _deselect_all_values(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if not item.isHidden():
                item.setCheckState(Qt.CheckState.Unchecked)

    def _on_op_changed(self, idx: int):
        op_text = self.combo_op.currentText()
        is_between = "Between" in op_text
        is_null_check = "Null" in op_text

        self.txt_val1.setVisible(not is_null_check)
        self.txt_val2.setVisible(is_between)

    def _load_current_filter(self):
        if not self.current_filter:
            return

        f_type = self.current_filter.get("type")
        if f_type == "values":
            if hasattr(self, "radio_values"):
                self.radio_values.setChecked(True)
            selected_set = set(self.current_filter.get("values", []))
            include_null = self.current_filter.get("include_null", True)

            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                raw_val = item.data(Qt.ItemDataRole.UserRole)
                if raw_val is None:
                    item.setCheckState(Qt.CheckState.Checked if include_null else Qt.CheckState.Unchecked)
                else:
                    item.setCheckState(Qt.CheckState.Checked if raw_val in selected_set else Qt.CheckState.Unchecked)

        elif f_type == "condition" and hasattr(self, "radio_condition"):
            self.radio_condition.setChecked(True)
            op = self.current_filter.get("op", "=")
            for i in range(self.combo_op.count()):
                if f"({op})" in self.combo_op.itemText(i) or (op == "null" and "Is Null" in self.combo_op.itemText(i)) or (op == "not_null" and "Is Not Null" in self.combo_op.itemText(i)) or (op == "between" and "Between" in self.combo_op.itemText(i)):
                    self.combo_op.setCurrentIndex(i)
                    break
            self.txt_val1.setText(str(self.current_filter.get("val1", "") or ""))
            self.txt_val2.setText(str(self.current_filter.get("val2", "") or ""))

    def _on_clear_filter(self):
        self._filter_result = {"type": "clear"}
        self.accept()

    def _on_apply(self):
        # Determine mode
        is_condition_mode = (hasattr(self, "radio_condition") and self.radio_condition.isChecked())

        if is_condition_mode:
            op_text = self.combo_op.currentText()
            if "Is Null" in op_text and "Not" not in op_text:
                op = "null"
            elif "Is Not Null" in op_text:
                op = "not_null"
            elif "Between" in op_text:
                op = "between"
            elif ">=" in op_text:
                op = ">="
            elif ">" in op_text:
                op = ">"
            elif "<=" in op_text:
                op = "<="
            elif "<" in op_text:
                op = "<"
            elif "!=" in op_text:
                op = "!="
            else:
                op = "="

            val1 = self.txt_val1.text().strip()
            val2 = self.txt_val2.text().strip()

            if op not in ("null", "not_null") and not val1:
                QMessageBox.warning(self, "Filter Error", "Please enter a value for the filter condition.")
                return

            self._filter_result = {
                "type": "condition",
                "col": self.col_name,
                "op": op,
                "val1": val1,
                "val2": val2,
                "description": f"{self.col_name} {op} {val1}" if op != "between" else f"{self.col_name} between [{val1}, {val2}]",
            }
        else:
            # Checkbox values list
            selected_values = set()
            include_null = False
            total_items = self.list_widget.count()
            selected_count = 0

            for i in range(total_items):
                item = self.list_widget.item(i)
                if item.checkState() == Qt.CheckState.Checked:
                    selected_count += 1
                    raw_val = item.data(Qt.ItemDataRole.UserRole)
                    if raw_val is None:
                        include_null = True
                    else:
                        selected_values.add(raw_val)

            if selected_count == total_items:
                # All selected -> Clear filter
                self._filter_result = {"type": "clear"}
            elif selected_count == 0:
                QMessageBox.warning(self, "Filter Warning", "Please select at least one value to filter.")
                return
            else:
                self._filter_result = {
                    "type": "values",
                    "col": self.col_name,
                    "values": list(selected_values),
                    "include_null": include_null,
                    "description": f"{self.col_name} in ({len(selected_values) + (1 if include_null else 0)} values)",
                }

        self.accept()

    def get_filter(self) -> Optional[Dict[str, Any]]:
        return self._filter_result
