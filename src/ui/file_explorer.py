"""
File Explorer widget for browsing directory trees and filtering .parquet files.
"""
from __future__ import annotations

import os
import subprocess
from PySide6.QtCore import Qt, Signal, QDir
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeView,
    QFileSystemModel,
    QFileDialog,
    QMenu,
    QHeaderView,
)
from PySide6.QtGui import QAction, QCursor


class FileExplorerWidget(QWidget):
    """File Explorer sidebar containing a directory tree filtered to directories and .parquet files."""

    file_selected = Signal(str)  # Emitted with the full absolute path of the selected parquet file

    def __init__(self, initial_dir: str = "", parent=None):
        super().__init__(parent)
        self._current_dir = initial_dir or os.getcwd()

        self._setup_ui()
        self._setup_model()
        self.set_directory(self._current_dir)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header Bar
        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)

        self.title_label = QLabel("📂 Parquet Explorer")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px;")

        self.btn_open_folder = QPushButton("Browse...")
        self.btn_open_folder.setToolTip("Select workspace folder")
        self.btn_open_folder.clicked.connect(self._browse_folder)

        self.btn_refresh = QPushButton("↻")
        self.btn_refresh.setFixedWidth(28)
        self.btn_refresh.setToolTip("Refresh file tree")
        self.btn_refresh.clicked.connect(self._refresh)

        header_layout.addWidget(self.title_label, 1)
        header_layout.addWidget(self.btn_open_folder)
        header_layout.addWidget(self.btn_refresh)
        layout.addLayout(header_layout)

        # Current Directory label / breadcrumb
        self.lbl_path = QLabel()
        self.lbl_path.setStyleSheet("color: #888899; font-size: 11px; padding: 2px 0;")
        self.lbl_path.setWordWrap(True)
        layout.addWidget(self.lbl_path)

        # File Tree View
        self.tree_view = QTreeView()
        self.tree_view.setAnimated(True)
        self.tree_view.setIndentation(16)
        self.tree_view.setSortingEnabled(True)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self._show_context_menu)
        self.tree_view.doubleClicked.connect(self._on_item_double_clicked)
        self.tree_view.clicked.connect(self._on_item_clicked)

        layout.addWidget(self.tree_view, 1)

    def _setup_model(self):
        self.model = QFileSystemModel(self)
        self.model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        self.model.setNameFilters(["*.parquet", "*.PARQUET"])
        self.model.setNameFilterDisables(False)  # Completely hide non-matching files

        self.tree_view.setModel(self.model)

        # Configure columns (Name, Size, Type, Date Modified)
        header = self.tree_view.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

    def set_directory(self, path: str):
        """Sets the root directory of the file explorer."""
        if not os.path.isdir(path):
            return

        self._current_dir = os.path.abspath(path)
        self.lbl_path.setText(f"📁 {self._current_dir}")
        self.model.setRootPath(self._current_dir)
        root_index = self.model.index(self._current_dir)
        self.tree_view.setRootIndex(root_index)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder Containing Parquet Files", self._current_dir
        )
        if folder:
            self.set_directory(folder)

    def _refresh(self):
        self.model.setRootPath("")
        self.set_directory(self._current_dir)

    def _on_item_clicked(self, index):
        file_path = self.model.filePath(index)
        if os.path.isfile(file_path) and file_path.lower().endswith(".parquet"):
            self.file_selected.emit(file_path)

    def _on_item_double_clicked(self, index):
        file_path = self.model.filePath(index)
        if os.path.isfile(file_path) and file_path.lower().endswith(".parquet"):
            self.file_selected.emit(file_path)

    def _show_context_menu(self, pos):
        index = self.tree_view.indexAt(pos)
        if not index.isValid():
            return

        file_path = self.model.filePath(index)
        is_file = os.path.isfile(file_path)
        is_parquet = is_file and file_path.lower().endswith(".parquet")

        menu = QMenu(self)

        if is_parquet:
            action_open = menu.addAction("Open in Editor")
            action_open.triggered.connect(lambda: self.file_selected.emit(file_path))
            menu.addSeparator()

        action_reveal = menu.addAction("Show in File Explorer")
        action_reveal.triggered.connect(lambda: self._reveal_in_explorer(file_path))

        action_copy_path = menu.addAction("Copy Absolute Path")
        action_copy_path.triggered.connect(lambda: self._copy_path(file_path))

        menu.exec(QCursor.pos())

    def _reveal_in_explorer(self, path: str):
        if os.path.exists(path):
            subprocess.Popen(f'explorer /select,"{os.path.abspath(path)}"')

    def _copy_path(self, path: str):
        from PySide6.QtGui import QGuiApplication
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(os.path.abspath(path))
