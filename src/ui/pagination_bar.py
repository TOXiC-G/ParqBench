"""
Pagination Control Widget for Parquet Data Grid.
Provides page navigation, page size selection, and enable/disable pagination toggling.
"""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QSpinBox,
    QCheckBox,
)


class PaginationBar(QWidget):
    """Bottom navigation bar for paginating large tabular datasets."""

    page_changed = Signal(int)        # 1-indexed page number
    page_size_changed = Signal(int)   # -1 for All (disabled)
    pagination_toggled = Signal(bool) # True = Enabled, False = Disabled

    def __init__(self, default_page_size: int = 250, parent=None):
        super().__init__(parent)
        self._current_page: int = 1
        self._total_pages: int = 1
        self._total_rows: int = 0
        self._page_size: int = default_page_size
        self._is_enabled: bool = True

        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background-color: #141418; border-top: 1px solid #282830; padding: 2px;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        # Pagination Enabled checkbox
        self.chk_enable = QCheckBox("Paginated View")
        self.chk_enable.setChecked(True)
        self.chk_enable.setToolTip("Toggle pagination on/off for smooth performance vs single continuous view")
        self.chk_enable.stateChanged.connect(self._on_enable_toggled)
        layout.addWidget(self.chk_enable)

        layout.addSpacing(10)

        # Page Size Combo
        lbl_page_size = QLabel("Rows per page:")
        lbl_page_size.setStyleSheet("color: #9da0aa; font-size: 11px;")
        layout.addWidget(lbl_page_size)

        self.combo_page_size = QComboBox()
        self.combo_page_size.addItems(["50", "100", "250", "500", "1000", "All (No pagination)"])
        self.combo_page_size.setCurrentText("250")
        self.combo_page_size.currentIndexChanged.connect(self._on_page_size_selected)
        layout.addWidget(self.combo_page_size)

        layout.addSpacing(16)

        # Navigation Controls
        self.btn_first = QPushButton("⏮")
        self.btn_first.setFixedWidth(28)
        self.btn_first.setToolTip("First page")
        self.btn_first.clicked.connect(lambda: self.set_page(1))
        layout.addWidget(self.btn_first)

        self.btn_prev = QPushButton("◀")
        self.btn_prev.setFixedWidth(28)
        self.btn_prev.setToolTip("Previous page")
        self.btn_prev.clicked.connect(lambda: self.set_page(self._current_page - 1))
        layout.addWidget(self.btn_prev)

        lbl_page = QLabel("Page")
        lbl_page.setStyleSheet("color: #9da0aa; font-size: 11px;")
        layout.addWidget(lbl_page)

        self.spin_page = QSpinBox()
        self.spin_page.setMinimum(1)
        self.spin_page.setMaximum(1)
        self.spin_page.setValue(1)
        self.spin_page.setFixedWidth(65)
        self.spin_page.valueChanged.connect(self._on_spin_page_changed)
        layout.addWidget(self.spin_page)

        self.lbl_total_pages = QLabel("of 1")
        self.lbl_total_pages.setStyleSheet("color: #9da0aa; font-size: 11px;")
        layout.addWidget(self.lbl_total_pages)

        self.btn_next = QPushButton("▶")
        self.btn_next.setFixedWidth(28)
        self.btn_next.setToolTip("Next page")
        self.btn_next.clicked.connect(lambda: self.set_page(self._current_page + 1))
        layout.addWidget(self.btn_next)

        self.btn_last = QPushButton("⏭")
        self.btn_last.setFixedWidth(28)
        self.btn_last.setToolTip("Last page")
        self.btn_last.clicked.connect(lambda: self.set_page(self._total_pages))
        layout.addWidget(self.btn_last)

        layout.addStretch(1)

        # Status text
        self.lbl_range_info = QLabel("Showing 0 - 0 of 0 rows")
        self.lbl_range_info.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: 500;")
        layout.addWidget(self.lbl_range_info)

    def update_pagination(self, total_rows: int):
        """Updates page counts and button states based on total rows."""
        self._total_rows = total_rows

        if not self._is_enabled or self._page_size <= 0:
            self._total_pages = 1
            self._current_page = 1
            self.spin_page.setMaximum(1)
            self.spin_page.setValue(1)
            self.lbl_total_pages.setText("of 1")
            self._set_nav_buttons_enabled(False)
            self.lbl_range_info.setText(f"Showing all {total_rows:,} rows")
            return

        self._total_pages = max(1, (total_rows + self._page_size - 1) // self._page_size)
        if self._current_page > self._total_pages:
            self._current_page = self._total_pages

        self.spin_page.blockSignals(True)
        self.spin_page.setMaximum(self._total_pages)
        self.spin_page.setValue(self._current_page)
        self.spin_page.blockSignals(False)

        self.lbl_total_pages.setText(f"of {self._total_pages:,}")
        self._set_nav_buttons_enabled(True)

        # Compute range
        if total_rows == 0:
            self.lbl_range_info.setText("0 rows")
        else:
            start_r = (self._current_page - 1) * self._page_size + 1
            end_r = min(self._current_page * self._page_size, total_rows)
            self.lbl_range_info.setText(f"Showing {start_r:,} - {end_r:,} of {total_rows:,} rows")

    def set_page(self, page: int):
        target = max(1, min(page, self._total_pages))
        if target != self._current_page:
            self._current_page = target
            self.spin_page.blockSignals(True)
            self.spin_page.setValue(self._current_page)
            self.spin_page.blockSignals(False)
            self.page_changed.emit(self._current_page)
            self.update_pagination(self._total_rows)

    @property
    def current_page(self) -> int:
        return self._current_page

    @property
    def page_size(self) -> int:
        return self._page_size if self._is_enabled else -1

    @property
    def is_pagination_enabled(self) -> bool:
        return self._is_enabled

    def _on_enable_toggled(self, state):
        self._is_enabled = (state == Qt.CheckState.Checked.value or state == True)
        self.combo_page_size.setEnabled(self._is_enabled)
        self.pagination_toggled.emit(self._is_enabled)

    def _on_page_size_selected(self, index: int):
        text = self.combo_page_size.currentText()
        if "All" in text:
            self._page_size = -1
            self.chk_enable.setChecked(False)
        else:
            self._page_size = int(text)
            if not self.chk_enable.isChecked():
                self.chk_enable.setChecked(True)
            self.page_size_changed.emit(self._page_size)

    def _on_spin_page_changed(self, value: int):
        self.set_page(value)

    def _set_nav_buttons_enabled(self, enabled: bool):
        self.btn_first.setEnabled(enabled and self._current_page > 1)
        self.btn_prev.setEnabled(enabled and self._current_page > 1)
        self.btn_next.setEnabled(enabled and self._current_page < self._total_pages)
        self.btn_last.setEnabled(enabled and self._current_page < self._total_pages)
        self.spin_page.setEnabled(enabled)
