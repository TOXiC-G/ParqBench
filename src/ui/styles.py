"""
Modern styling and themes for the Parquet Editor application.
Provides a clean, Excel-inspired modern aesthetic with dark and light theme palettes.
"""

MODERN_DARK_THEME = """
QMainWindow, QDialog, QWidget {
    background-color: #1e1e24;
    color: #e0e0e0;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}

/* Menu Bar & Menus */
QMenuBar {
    background-color: #18181c;
    color: #e0e0e0;
    border-bottom: 1px solid #2d2d34;
    padding: 2px 6px;
}
QMenuBar::item {
    background: transparent;
    padding: 6px 10px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background-color: #2b2b36;
    color: #ffffff;
}
QMenu {
    background-color: #24242c;
    color: #e0e0e0;
    border: 1px solid #383844;
    border-radius: 6px;
    padding: 4px 0px;
}
QMenu::item {
    padding: 6px 24px 6px 28px;
}
QMenu::item:selected {
    background-color: #107c41;
    color: #ffffff;
}
QMenu::separator {
    height: 1px;
    background-color: #383844;
    margin: 4px 8px;
}

/* ToolBar */
QToolBar {
    background-color: #18181c;
    border-bottom: 1px solid #2d2d34;
    spacing: 6px;
    padding: 4px 8px;
}
QToolButton {
    background-color: #282832;
    color: #e0e0e0;
    border: 1px solid #383844;
    border-radius: 4px;
    padding: 5px 10px;
    font-weight: 500;
}
QToolButton:hover {
    background-color: #343442;
    border-color: #107c41;
    color: #ffffff;
}
QToolButton:pressed {
    background-color: #107c41;
    color: #ffffff;
}

/* Buttons */
QPushButton {
    background-color: #282832;
    color: #e0e0e0;
    border: 1px solid #383844;
    border-radius: 4px;
    padding: 6px 14px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #343442;
    border-color: #107c41;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #107c41;
    color: #ffffff;
}
QPushButton:disabled {
    background-color: #1c1c22;
    color: #555560;
    border-color: #26262e;
}
QPushButton#iconBtn {
    padding: 1px 2px;
    min-width: 0px;
    font-size: 12px;
}
QPushButton#primaryButton {
    background-color: #107c41;
    color: #ffffff;
    border: 1px solid #107c41;
}
QPushButton#primaryButton:hover {
    background-color: #148f4b;
}

QSpinBox {
    background-color: #141418;
    color: #ffffff;
    border: 1px solid #383844;
    border-radius: 4px;
    padding: 3px 5px;
}
QSpinBox:focus {
    border-color: #107c41;
}
QSpinBox::up-button, QSpinBox::down-button {
    width: 0px;
    height: 0px;
    border: none;
    background: none;
}

/* LineEdit / Search Input */
QLineEdit {
    background-color: #141418;
    color: #ffffff;
    border: 1px solid #383844;
    border-radius: 4px;
    padding: 5px 10px;
    selection-background-color: #107c41;
}
QLineEdit:focus {
    border: 1px solid #107c41;
    background-color: #181820;
}

/* Splitter */
QSplitter::handle {
    background-color: #2d2d34;
}
QSplitter::handle:horizontal {
    width: 3px;
}
QSplitter::handle:vertical {
    height: 3px;
}
QSplitter::handle:hover {
    background-color: #107c41;
}

/* File Tree View */
QTreeView {
    background-color: #16161a;
    color: #d0d0d8;
    border: 1px solid #2d2d34;
    border-radius: 4px;
    outline: 0;
    padding: 2px;
}
QTreeView::item {
    padding: 4px 6px;
    border-radius: 3px;
}
QTreeView::item:hover {
    background-color: #262630;
    color: #ffffff;
}
QTreeView::item:selected {
    background-color: #1b4d32;
    color: #ffffff;
}
QHeaderView::section {
    background-color: #1c1c22;
    color: #9da0aa;
    font-weight: 600;
    padding: 5px 8px;
    border: 1px solid #2d2d34;
}

/* Data Table View (Excel Look) */
QTableView {
    background-color: #141418;
    color: #f0f0f0;
    gridline-color: #2b2b34;
    border: 1px solid #2d2d34;
    border-radius: 4px;
    selection-background-color: #1b4d32;
    selection-color: #ffffff;
    outline: 0;
}
QTableView::item {
    padding: 4px 8px;
}
QTableView::item:selected {
    background-color: #164e31;
    color: #ffffff;
}
QTableView::item:focus {
    border: 2px solid #107c41;
}
QHeaderView::section:horizontal {
    background-color: #1f1f26;
    color: #b0b4c0;
    font-weight: 600;
    font-size: 12px;
    border: 1px solid #2b2b34;
    padding: 6px 10px;
}
QHeaderView::section:vertical {
    background-color: #1a1a20;
    color: #7a7e8c;
    font-size: 11px;
    border: 1px solid #2b2b34;
    padding: 4px 6px;
    text-align: center;
}

/* Status Bar */
QStatusBar {
    background-color: #121216;
    color: #9da0aa;
    border-top: 1px solid #282830;
    font-size: 12px;
    padding: 2px 8px;
}
QStatusBar QLabel {
    color: #b0b4c0;
    padding: 0 6px;
}

/* Scrollbars */
QScrollBar:vertical {
    background: #121216;
    width: 12px;
    margin: 0px;
    border: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}
QScrollBar::handle:vertical {
    background: #484b58;
    border: 1px solid #5a5e70;
    min-height: 36px;
    border-radius: 4px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover {
    background: #107c41;
    border-color: #159c52;
}
QScrollBar::handle:vertical:pressed {
    background: #139c52;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    width: 0px;
    height: 0px;
    background: none;
    border: none;
}

QScrollBar:horizontal {
    background: #121216;
    height: 12px;
    margin: 0px;
    border: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}
QScrollBar::handle:horizontal {
    background: #484b58;
    border: 1px solid #5a5e70;
    min-width: 36px;
    border-radius: 4px;
    margin: 2px;
}
QScrollBar::handle:horizontal:hover {
    background: #107c41;
    border-color: #159c52;
}
QScrollBar::handle:horizontal:pressed {
    background: #139c52;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    height: 0px;
    background: none;
    border: none;
}
QScrollBar::corner {
    background: #121216;
    border: none;
}
"""

MODERN_LIGHT_THEME = """
QMainWindow, QDialog, QWidget {
    background-color: #f7f9fa;
    color: #24292f;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}

QMenuBar {
    background-color: #ffffff;
    color: #24292f;
    border-bottom: 1px solid #e1e4e8;
    padding: 2px 6px;
}
QMenuBar::item:selected {
    background-color: #eef2f5;
}
QMenu {
    background-color: #ffffff;
    color: #24292f;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 4px 0px;
}
QMenu::item:selected {
    background-color: #107c41;
    color: #ffffff;
}

QToolBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e1e4e8;
    spacing: 6px;
    padding: 4px 8px;
}
QToolButton, QPushButton {
    background-color: #ffffff;
    color: #24292f;
    border: 1px solid #d0d7de;
    border-radius: 4px;
    padding: 5px 12px;
    font-weight: 500;
}
QToolButton:hover, QPushButton:hover {
    background-color: #f3f4f6;
    border-color: #107c41;
}
QToolButton:pressed, QPushButton:pressed {
    background-color: #107c41;
    color: #ffffff;
}
QPushButton#iconBtn {
    padding: 1px 2px;
    min-width: 0px;
    font-size: 12px;
}
QPushButton#primaryButton {
    background-color: #107c41;
    color: #ffffff;
    border: 1px solid #107c41;
}

QLineEdit {
    background-color: #ffffff;
    color: #24292f;
    border: 1px solid #d0d7de;
    border-radius: 4px;
    padding: 5px 10px;
}
QLineEdit:focus {
    border: 1px solid #107c41;
}

QSpinBox {
    background-color: #ffffff;
    color: #24292f;
    border: 1px solid #d0d7de;
    border-radius: 4px;
    padding: 3px 5px;
}
QSpinBox:focus {
    border-color: #107c41;
}
QSpinBox::up-button, QSpinBox::down-button {
    width: 0px;
    height: 0px;
    border: none;
    background: none;
}

QSplitter::handle {
    background-color: #e1e4e8;
}
QSplitter::handle:hover {
    background-color: #107c41;
}

QTreeView {
    background-color: #ffffff;
    color: #24292f;
    border: 1px solid #e1e4e8;
    border-radius: 4px;
}
QTreeView::item:hover {
    background-color: #f0f4f8;
}
QTreeView::item:selected {
    background-color: #d4edda;
    color: #155724;
}

QTableView {
    background-color: #ffffff;
    color: #24292f;
    gridline-color: #e1e4e8;
    border: 1px solid #e1e4e8;
    border-radius: 4px;
    selection-background-color: #c8e6c9;
    selection-color: #1b5e20;
}
QHeaderView::section:horizontal {
    background-color: #f1f3f5;
    color: #495057;
    font-weight: 600;
    border: 1px solid #e1e4e8;
    padding: 6px 10px;
}
QHeaderView::section:vertical {
    background-color: #f8f9fa;
    color: #868e96;
    border: 1px solid #e1e4e8;
    padding: 4px 6px;
}

QStatusBar {
    background-color: #f1f3f5;
    color: #6c757d;
    border-top: 1px solid #e1e4e8;
}

/* Light Theme Scrollbars */
QScrollBar:vertical {
    background: #eaedf0;
    width: 12px;
    margin: 0px;
    border: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}
QScrollBar::handle:vertical {
    background: #b0b6be;
    border: 1px solid #9aa0a8;
    min-height: 36px;
    border-radius: 4px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover {
    background: #107c41;
    border-color: #0d6334;
}
QScrollBar::handle:vertical:pressed {
    background: #0d6334;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    width: 0px;
    height: 0px;
    background: none;
    border: none;
}

QScrollBar:horizontal {
    background: #eaedf0;
    height: 12px;
    margin: 0px;
    border: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}
QScrollBar::handle:horizontal {
    background: #b0b6be;
    border: 1px solid #9aa0a8;
    min-width: 36px;
    border-radius: 4px;
    margin: 2px;
}
QScrollBar::handle:horizontal:hover {
    background: #107c41;
    border-color: #0d6334;
}
QScrollBar::handle:horizontal:pressed {
    background: #0d6334;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    height: 0px;
    background: none;
    border: none;
}
QScrollBar::corner {
    background: #eaedf0;
    border: none;
}
"""
