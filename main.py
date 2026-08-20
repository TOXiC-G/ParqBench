"""
Parquet Editor — Desktop Excel-like Tabular Suite
Main application entry point.
"""
from __future__ import annotations

import sys
import os

# Ensure local project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow


def main():
    # Enable High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Parquet Editor")
    app.setOrganizationName("Antigravity")

    # Check for initial file passed via CLI
    initial_file = None
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        initial_file = os.path.abspath(sys.argv[1])

    window = MainWindow(initial_file=initial_file)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
