"""
Search, filter and quick navigation toolbar for the data grid.
"""
from __future__ import annotations

from typing import List, Tuple
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QCheckBox,
    QSpinBox,
)


class SearchToolbar(QWidget):
    """Toolbar for searching text within the grid and jumping to specific rows."""

    search_requested = Signal(str, bool)  # (search_text, case_sensitive)
    navigate_match = Signal(int)         # direction: +1 for next, -1 for prev
    jump_to_row_requested = Signal(int)  # 0-indexed row number
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._matches: List[Tuple[int, int]] = []
        self._current_match_idx: int = -1

        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        lbl_find = QLabel("🔍 Find:")
        layout.addWidget(lbl_find)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search cell contents...")
        self.txt_search.setMinimumWidth(180)
        self.txt_search.textChanged.connect(self._on_search_text_changed)
        self.txt_search.returnPressed.connect(lambda: self.navigate_match.emit(1))
        layout.addWidget(self.txt_search)

        self.chk_case = QCheckBox("Match Case")
        self.chk_case.stateChanged.connect(lambda: self._on_search_text_changed(self.txt_search.text()))
        layout.addWidget(self.chk_case)

        self.btn_prev = QPushButton("◀")
        self.btn_prev.setFixedWidth(28)
        self.btn_prev.setToolTip("Previous match (Shift+F3)")
        self.btn_prev.clicked.connect(lambda: self.navigate_match.emit(-1))
        layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("▶")
        self.btn_next.setFixedWidth(28)
        self.btn_next.setToolTip("Next match (F3 or Enter)")
        self.btn_next.clicked.connect(lambda: self.navigate_match.emit(1))
        layout.addWidget(self.btn_next)

        self.lbl_match_count = QLabel("")
        self.lbl_match_count.setStyleSheet("color: #8888aa; font-size: 11px;")
        layout.addWidget(self.lbl_match_count)

        layout.addSpacing(16)

        # Jump to row
        lbl_jump = QLabel("Go to row:")
        layout.addWidget(lbl_jump)

        self.spin_row = QSpinBox()
        self.spin_row.setMinimum(1)
        self.spin_row.setMaximum(1)
        self.spin_row.setFixedWidth(80)
        layout.addWidget(self.spin_row)

        self.btn_jump = QPushButton("Go")
        self.btn_jump.clicked.connect(self._on_jump_clicked)
        layout.addWidget(self.btn_jump)

        layout.addStretch(1)

        # Close toolbar button
        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedWidth(24)
        self.btn_close.setToolTip("Close search bar (Esc)")
        self.btn_close.clicked.connect(self.closed.emit)
        layout.addWidget(self.btn_close)

    def set_max_rows(self, count: int):
        """Updates maximum row count in the jump-to-row spinner."""
        self.spin_row.setMaximum(max(1, count))

    def focus_search(self):
        """Focuses and selects text in the search bar."""
        self.txt_search.setFocus()
        self.txt_search.selectAll()

    def update_match_status(self, current_idx: int, total_matches: int):
        """Updates status label e.g. '3 of 15 matches'."""
        if total_matches == 0:
            if self.txt_search.text():
                self.lbl_match_count.setText("No matches")
            else:
                self.lbl_match_count.setText("")
        else:
            self.lbl_match_count.setText(f"{current_idx + 1} of {total_matches} matches")

    def _on_search_text_changed(self, text: str):
        self.search_requested.emit(text, self.chk_case.isChecked())

    def _on_jump_clicked(self):
        row = self.spin_row.value() - 1  # 0-indexed
        self.jump_to_row_requested.emit(row)
