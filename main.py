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


def resolve_icon_path() -> Optional[str]:
    """Find application icon across development and PyInstaller bundled directory structures."""
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "assets", "icon.ico"))
        candidates.append(os.path.join(exe_dir, "assets", "icon.png"))
        if hasattr(sys, "_MEIPASS"):
            candidates.append(os.path.join(sys._MEIPASS, "assets", "icon.ico"))
            candidates.append(os.path.join(sys._MEIPASS, "assets", "icon.png"))
    candidates.append(os.path.join(PROJECT_ROOT, "assets", "icon.ico"))
    candidates.append(os.path.join(PROJECT_ROOT, "assets", "icon.png"))
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


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
    icon_path = resolve_icon_path()
    if icon_path:
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)

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
    if icon_path:
        window.setWindowIcon(QIcon(icon_path))
    if initial_dir and os.path.isdir(initial_dir):
        window.open_directory(initial_dir)

    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
