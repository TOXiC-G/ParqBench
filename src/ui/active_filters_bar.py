"""
Active Filters Panel Bar.
Displays pills/badges for all active column filters with one-click removal and clear-all.
"""
from __future__ import annotations

from typing import Dict, Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QFrame,
)


class FilterPill(QFrame):
    """Badge representation for an active column filter."""

    remove_requested = Signal(str)  # Emitted with column name to remove
    clicked = Signal(str)           # Emitted with column name to edit filter

    def __init__(self, col_name: str, description: str, parent=None):
        super().__init__(parent)
        self.col_name = col_name
        self.setStyleSheet("""
            QFrame {
                background-color: #24352a;
                border: 1px solid #107c41;
                border-radius: 12px;
                padding: 1px 6px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(6)

        lbl_desc = QLabel(f"<b>{col_name}:</b> {description}")
        lbl_desc.setStyleSheet("color: #a3e635; font-size: 11px; background: transparent; border: none;")
        layout.addWidget(lbl_desc)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(16, 16)
        btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #e0e0e0;
                border: none;
                font-size: 11px;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:hover {
                color: #ef4444;
            }
        """)
        btn_close.clicked.connect(lambda: self.remove_requested.emit(self.col_name))
        layout.addWidget(btn_close)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.col_name)
        super().mousePressEvent(event)


class ActiveFiltersBar(QWidget):
    """Horizontal panel displaying all currently active filters."""

    filter_removed = Signal(str)   # column name
    filter_edit_requested = Signal(str)
    clear_all_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.setVisible(False)

    def _setup_ui(self):
        self.setStyleSheet("background-color: #16181f; border-bottom: 1px solid #2d2d38;")
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 4, 10, 4)
        main_layout.setSpacing(8)

        lbl_icon = QLabel("🔍 Active Filters:")
        lbl_icon.setStyleSheet("color: #9da0aa; font-weight: bold; font-size: 11px;")
        main_layout.addWidget(lbl_icon)

        # Scrollable area for filter pills
        self.pills_container = QWidget()
        self.pills_container.setStyleSheet("background: transparent;")
        self.pills_layout = QHBoxLayout(self.pills_container)
        self.pills_layout.setContentsMargins(0, 0, 0, 0)
        self.pills_layout.setSpacing(6)
        self.pills_layout.addStretch(1)

        scroll_area = QScrollArea()
        scroll_area.setWidget(self.pills_container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedHeight(30)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("background: transparent; border: none;")
        main_layout.addWidget(scroll_area, 1)

        self.btn_clear_all = QPushButton("Clear All")
        self.btn_clear_all.setFixedHeight(22)
        self.btn_clear_all.setStyleSheet("""
            QPushButton {
                background-color: #2b2024;
                color: #f87171;
                border: 1px solid #7f1d1d;
                border-radius: 3px;
                font-size: 11px;
                padding: 1px 8px;
            }
            QPushButton:hover {
                background-color: #991b1b;
                color: #ffffff;
            }
        """)
        self.btn_clear_all.clicked.connect(self.clear_all_requested.emit)
        main_layout.addWidget(self.btn_clear_all)

    def update_filters(self, active_filters: Dict[str, Dict[str, Any]]):
        """Updates displayed pills matching current active filters dict."""
        # Clear existing pills
        while self.pills_layout.count() > 1:
            item = self.pills_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not active_filters:
            self.setVisible(False)
            return

        self.setVisible(True)
        for col_name, f_info in active_filters.items():
            desc = f_info.get("description", "Filtered")
            # Truncate long descriptions if needed
            short_desc = desc if len(desc) <= 40 else desc[:37] + "..."
            pill = FilterPill(col_name, short_desc, self)
            pill.remove_requested.connect(self.filter_removed.emit)
            pill.clicked.connect(self.filter_edit_requested.emit)
            self.pills_layout.insertWidget(self.pills_layout.count() - 1, pill)
