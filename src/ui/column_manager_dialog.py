"""
Column Visibility Manager Dialog.
Allows users to show/hide columns from the viewport without removing them from exports or saves.
"""
from __future__ import annotations

from typing import List, Set
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
    QMessageBox,
)


class ColumnManagerDialog(QDialog):
    """Dialog allowing users to toggle column visibility in the table view."""

    def __init__(self, col_names: List[str], hidden_cols: Set[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Column Visibility")
        self.resize(360, 440)
        self.col_names = col_names
        self.hidden_cols = set(hidden_cols)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        lbl_info = QLabel("Check columns to display in grid. (Hidden columns remain intact for exports/saves)")
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet("color: #9da0aa; font-size: 12px;")
        layout.addWidget(lbl_info)

        # Search filter
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search columns...")
        self.txt_search.textChanged.connect(self._filter_items)
        layout.addWidget(self.txt_search)

        # Quick action buttons
        btn_row = QHBoxLayout()
        btn_all = QPushButton("Show All")
        btn_all.clicked.connect(self._show_all)
        btn_none = QPushButton("Hide All")
        btn_none.clicked.connect(self._hide_all)
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # Column list
        self.list_widget = QListWidget()
        for col in self.col_names:
            item = QListWidgetItem(str(col))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            is_visible = col not in self.hidden_cols
            item.setCheckState(Qt.CheckState.Checked if is_visible else Qt.CheckState.Unchecked)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget, 1)

        # Dialog buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch(1)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_apply = QPushButton("Apply")
        btn_apply.setObjectName("primaryButton")
        btn_apply.clicked.connect(self._on_apply)
        btn_box.addWidget(btn_apply)

        layout.addLayout(btn_box)

    def _filter_items(self, text: str):
        query = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(query not in item.text().lower())

    def _show_all(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if not item.isHidden():
                item.setCheckState(Qt.CheckState.Checked)

    def _hide_all(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if not item.isHidden():
                item.setCheckState(Qt.CheckState.Unchecked)

    def _on_apply(self):
        visible_count = 0
        new_hidden = set()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            col = item.text()
            if item.checkState() == Qt.CheckState.Checked:
                visible_count += 1
            else:
                new_hidden.add(col)

        if visible_count == 0:
            QMessageBox.warning(self, "Visibility Warning", "You must keep at least one column visible.")
            return

        self.hidden_cols = new_hidden
        self.accept()

    def get_hidden_columns(self) -> Set[str]:
        return self.hidden_cols
