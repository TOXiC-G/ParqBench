"""
ParqBench — Desktop Excel-like Tabular Suite for Apache Parquet
Main application entry point.
"""
from __future__ import annotations

import sys
import os

# Ensure local project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Set Windows Application User Model ID for proper taskbar grouping and branding
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("parqbench.desktop.app.1.0")
    except Exception:
        pass

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from src import __version__, __app_name__
from src.ui.main_window import MainWindow


def main():
    # Enable High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName(__app_name__)
    app.setApplicationVersion(__version__)

    # Set application-wide icon
    icon_path = os.path.join(PROJECT_ROOT, "assets", "icon.ico")
    if not os.path.exists(icon_path):
        icon_path = os.path.join(PROJECT_ROOT, "assets", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Check for initial file or folder passed via CLI
    initial_file = None
    initial_dir = None
    if len(sys.argv) > 1:
        target = os.path.abspath(sys.argv[1].strip('"'))
        if os.path.isfile(target):
            initial_file = target
        elif os.path.isdir(target):
            initial_dir = target

    window = MainWindow(initial_file=initial_file)
    if initial_dir and os.path.isdir(initial_dir):
        window.open_directory(initial_dir)

    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
