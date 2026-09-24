"""
ParqBench Software Update Dialog
Presents update status, release notes, live download progress bar,
and one-click non-admin install and restart.
"""
from __future__ import annotations

import os
import sys
from typing import Optional
from PySide6.QtCore import Qt, QThread, QUrl
from PySide6.QtGui import QFont, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QFrame,
    QSizePolicy,
    QMessageBox,
)

from src import __version__, __app_name__
from src.engine.updater import (
    UpdateInfo,
    UpdateCheckWorker,
    UpdateDownloadWorker,
    launch_installer_and_exit,
    GITHUB_REPO,
)


class UpdaterDialog(QDialog):
    """Software update modal displaying release info, download progress, and install action."""

    def __init__(self, parent=None, initial_info: Optional[UpdateInfo] = None):
        super().__init__(parent)
        self.setWindowTitle(f"{__app_name__} — Software Update")
        self.resize(560, 480)
        self.setMinimumSize(480, 400)

        self._info: Optional[UpdateInfo] = initial_info
        self._check_thread: Optional[QThread] = None
        self._download_thread: Optional[QThread] = None
        self._download_worker: Optional[UpdateDownloadWorker] = None
        self._downloaded_file: Optional[str] = None

        self._setup_ui()

        # Set dialog icon if present
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        icon_path = os.path.join(repo_root, "assets", "icon.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(repo_root, "assets", "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        if self._info is not None:
            self._display_update_info(self._info)
        else:
            self.start_check()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header Frame
        header = QFrame()
        header.setStyleSheet("background: #181822; border-radius: 8px; padding: 12px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 10, 12, 10)

        header_text_layout = QVBoxLayout()
        self.lbl_title = QLabel("Software Update")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        header_text_layout.addWidget(self.lbl_title)

        self.lbl_subtitle = QLabel(f"Current version: v{__version__}")
        self.lbl_subtitle.setStyleSheet("font-size: 12px; color: #94a3b8;")
        header_text_layout.addWidget(self.lbl_subtitle)

        h_layout.addLayout(header_text_layout, 1)

        self.lbl_badge = QLabel("Checking…")
        self.lbl_badge.setStyleSheet(
            "background: #334155; color: #e2e8f0; font-size: 11px; "
            "font-weight: bold; border-radius: 12px; padding: 4px 10px;"
        )
        h_layout.addWidget(self.lbl_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(header)

        # Status Message Banner
        self.lbl_status = QLabel("Checking for newer versions…")
        self.lbl_status.setStyleSheet("font-size: 13px; color: #cbd5e1; font-weight: 500;")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        # Release Notes area
        notes_label = QLabel("Release Notes:")
        notes_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #94a3b8;")
        layout.addWidget(notes_label)

        self.txt_notes = QTextEdit()
        self.txt_notes.setReadOnly(True)
        self.txt_notes.setStyleSheet(
            "background: #1e1e2d; color: #f1f5f9; border: 1px solid #334155; "
            "border-radius: 6px; font-family: 'Segoe UI', sans-serif; font-size: 12px; padding: 8px;"
        )
        self.txt_notes.setPlaceholderText("Release notes will appear here once retrieved.")
        layout.addWidget(self.txt_notes, 1)

        # Download Progress Area (hidden by default)
        self.progress_frame = QFrame()
        p_layout = QVBoxLayout(self.progress_frame)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(4)

        self.lbl_progress_detail = QLabel("Downloading update...")
        self.lbl_progress_detail.setStyleSheet("font-size: 11px; color: #38bdf8;")
        p_layout.addWidget(self.lbl_progress_detail)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background: #1e1e2d; border: 1px solid #334155; border-radius: 4px; height: 18px; text-align: center; color: white; font-weight: bold; } "
            "QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #06b6d4); border-radius: 3px; }"
        )
        p_layout.addWidget(self.progress_bar)
        self.progress_frame.setVisible(False)
        layout.addWidget(self.progress_frame)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_github = QPushButton("🌐 View on GitHub")
        self.btn_github.setStyleSheet(
            "background: #1e293b; color: #cbd5e1; border: 1px solid #475569; "
            "border-radius: 5px; padding: 6px 12px;"
        )
        self.btn_github.clicked.connect(self._open_github)
        self.btn_github.setVisible(False)
        btn_layout.addWidget(self.btn_github)

        btn_layout.addStretch(1)

        self.btn_check_again = QPushButton("🔄 Check Again")
        self.btn_check_again.setStyleSheet(
            "background: #1e293b; color: #cbd5e1; border: 1px solid #475569; "
            "border-radius: 5px; padding: 6px 14px;"
        )
        self.btn_check_again.clicked.connect(self.start_check)
        self.btn_check_again.setVisible(False)
        btn_layout.addWidget(self.btn_check_again)

        self.btn_action = QPushButton("Download & Install")
        self.btn_action.setStyleSheet(
            "background: #10b981; color: white; font-weight: bold; "
            "border-radius: 5px; padding: 6px 16px;"
        )
        self.btn_action.clicked.connect(self._handle_action_click)
        self.btn_action.setVisible(False)
        btn_layout.addWidget(self.btn_action)

        self.btn_close = QPushButton("Close")
        self.btn_close.setStyleSheet(
            "background: #334155; color: white; border-radius: 5px; padding: 6px 14px;"
        )
        self.btn_close.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    # =========================================================================
    # Check Logic
    # =========================================================================

    def start_check(self):
        """Initiate background update check."""
        self.lbl_badge.setText("Checking…")
        self.lbl_badge.setStyleSheet(
            "background: #334155; color: #e2e8f0; font-size: 11px; "
            "font-weight: bold; border-radius: 12px; padding: 4px 10px;"
        )
        self.lbl_status.setText("Connecting to update server…")
        self.btn_action.setVisible(False)
        self.btn_check_again.setVisible(False)
        self.btn_github.setVisible(False)
        self.progress_frame.setVisible(False)
        self.txt_notes.setPlainText("Querying latest release information...")

        self._check_thread = QThread()
        worker = UpdateCheckWorker(GITHUB_REPO)
        worker.moveToThread(self._check_thread)
        self._check_thread.started.connect(worker.run)
        worker.check_finished.connect(self._on_check_finished)
        worker.check_finished.connect(self._check_thread.quit)
        self._check_worker = worker
        self._check_thread.start()

    def _on_check_finished(self, info: Optional[UpdateInfo], error: str):
        if error:
            self.lbl_badge.setText("Error")
            self.lbl_badge.setStyleSheet(
                "background: #7f1d1d; color: #fecaca; font-size: 11px; "
                "font-weight: bold; border-radius: 12px; padding: 4px 10px;"
            )
            self.lbl_status.setText(f"❌ {error}")
            self.txt_notes.setPlainText(
                f"Could not reach update server:\n{error}\n\n"
                "Please verify your internet connection or check GitHub directly."
            )
            self.btn_check_again.setVisible(True)
            self.btn_github.setVisible(True)
            return

        self._info = info
        self._display_update_info(info)

    def _display_update_info(self, info: UpdateInfo):
        self.btn_github.setVisible(bool(info.html_url))
        self.txt_notes.setPlainText(info.release_notes)

        if info.is_newer:
            self.lbl_badge.setText(f"v{info.latest_version} Available")
            self.lbl_badge.setStyleSheet(
                "background: #065f46; color: #6ee7b7; font-size: 11px; "
                "font-weight: bold; border-radius: 12px; padding: 4px 10px;"
            )
            self.lbl_status.setText(
                f"🚀 A newer version is available: <b>v{info.latest_version}</b> (You have v{info.current_version})"
            )
            if info.download_url:
                self.btn_action.setText("Download & Install Update")
                self.btn_action.setStyleSheet(
                    "background: #10b981; color: white; font-weight: bold; "
                    "border-radius: 5px; padding: 6px 16px;"
                )
                self.btn_action.setVisible(True)
            else:
                self.lbl_status.setText(
                    f"🚀 A newer version is available: <b>v{info.latest_version}</b>. "
                    "Installer asset not attached yet; click below to download from GitHub."
                )
                self.btn_action.setText("Open GitHub Release")
                self.btn_action.setVisible(True)
        else:
            self.lbl_badge.setText("Up to Date")
            self.lbl_badge.setStyleSheet(
                "background: #1e3a8a; color: #93c5fd; font-size: 11px; "
                "font-weight: bold; border-radius: 12px; padding: 4px 10px;"
            )
            self.lbl_status.setText(f"✅ You're up to date! ParqBench v{__version__} is the latest version.")
            self.btn_check_again.setVisible(True)

    # =========================================================================
    # Download & Install Action
    # =========================================================================

    def _handle_action_click(self):
        if not self._info:
            return

        # If download already finished, trigger install
        if self._downloaded_file and os.path.exists(self._downloaded_file):
            self._install_downloaded()
            return

        if not self._info.download_url:
            self._open_github()
            return

        # Start downloading
        self.btn_action.setEnabled(False)
        self.btn_action.setText("Downloading…")
        self.btn_check_again.setVisible(False)
        self.progress_frame.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_progress_detail.setText("Connecting to download server...")

        self._download_thread = QThread()
        self._download_worker = UpdateDownloadWorker(
            self._info.download_url,
            self._info.asset_name or f"ParqBench-Setup-v{self._info.latest_version}.exe",
        )
        self._download_worker.moveToThread(self._download_thread)
        self._download_thread.started.connect(self._download_worker.run)
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.download_finished.connect(self._on_download_finished)
        self._download_worker.download_failed.connect(self._on_download_failed)
        self._download_worker.download_finished.connect(self._download_thread.quit)
        self._download_worker.download_failed.connect(self._download_thread.quit)
        self._download_thread.start()

    def _on_download_progress(self, downloaded: int, total: int, pct: float):
        self.progress_bar.setValue(int(pct))
        down_mb = downloaded / (1024 * 1024)
        total_mb = total / (1024 * 1024)
        if total > 0:
            self.lbl_progress_detail.setText(
                f"Downloading update: {down_mb:.1f} MB / {total_mb:.1f} MB ({pct:.1f}%)"
            )
        else:
            self.lbl_progress_detail.setText(f"Downloading update: {down_mb:.1f} MB")

    def _on_download_finished(self, local_path: str):
        self._downloaded_file = local_path
        self.progress_bar.setValue(100)
        self.lbl_progress_detail.setText("✅ Download completed!")
        self.btn_action.setEnabled(True)
        self.btn_action.setText("Install & Restart Now")
        self.btn_action.setStyleSheet(
            "background: #0284c7; color: white; font-weight: bold; "
            "border-radius: 5px; padding: 6px 16px;"
        )
        self.lbl_status.setText(
            "<b>Update ready to install!</b> ParqBench will close and launch the non-admin installer."
        )

    def _on_download_failed(self, error: str):
        self.btn_action.setEnabled(True)
        self.btn_action.setText("Retry Download")
        self.lbl_progress_detail.setText(f"❌ Download failed: {error}")
        QMessageBox.warning(self, "Download Failed", f"Failed to download update:\n{error}")

    def _install_downloaded(self):
        if not self._downloaded_file or not os.path.exists(self._downloaded_file):
            QMessageBox.critical(self, "Error", "Downloaded installer file not found.")
            return

        confirm = QMessageBox.question(
            self,
            "Install Update",
            "ParqBench will now close and launch the update installer. Proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                launch_installer_and_exit(self._downloaded_file)
            except Exception as e:
                QMessageBox.critical(self, "Launch Error", f"Failed to launch installer:\n{str(e)}")

    def _open_github(self):
        url = self._info.html_url if (self._info and self._info.html_url) else f"https://github.com/{GITHUB_REPO}/releases"
        QDesktopServices.openUrl(QUrl(url))

    def closeEvent(self, event):
        # Cancel ongoing download if in progress
        if self._download_worker:
            self._download_worker.cancel()
        super().closeEvent(event)
