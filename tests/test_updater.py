"""
Unit tests for the Software Updater Engine, Settings Persistence, and Update Dialog.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

app = QApplication.instance()
if app is None:
    app = QApplication([])

from src import __version__
from src.engine.updater import (
    parse_semver,
    is_version_newer,
    UpdateInfo,
    fetch_latest_release,
)
from src.ui.updater_dialog import UpdaterDialog
from src.ui.main_window import MainWindow


class TestUpdaterEngine(unittest.TestCase):

    def test_parse_semver(self):
        self.assertEqual(parse_semver("1.0.0"), (1, 0, 0))
        self.assertEqual(parse_semver("v1.2.3-beta"), (1, 2, 3))
        self.assertEqual(parse_semver("2.10.4"), (2, 10, 4))
        self.assertEqual(parse_semver("invalid"), (0,))

    def test_is_version_newer(self):
        self.assertTrue(is_version_newer("1.0.1", "1.0.0"))
        self.assertTrue(is_version_newer("2.0.0", "1.9.9"))
        self.assertTrue(is_version_newer("1.10.0", "1.2.0"))
        self.assertFalse(is_version_newer("1.0.0", "1.0.0"))
        self.assertFalse(is_version_newer("0.9.9", "1.0.0"))

    @patch("urllib.request.urlopen")
    def test_fetch_latest_release_newer(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b"""{
            "tag_name": "v1.2.0",
            "body": "### Changes\\n- Performance improvements\\n- New update checker",
            "html_url": "https://github.com/TOXiC-G/ParqBench/releases/tag/v1.2.0",
            "assets": [
                {
                    "name": "ParqBench-Setup-x64.exe",
                    "browser_download_url": "https://github.com/downloads/ParqBench-Setup-x64.exe",
                    "size": 25000000
                }
            ]
        }"""
        mock_urlopen.return_value.__enter__.return_value = mock_response

        info = fetch_latest_release()
        self.assertEqual(info.latest_version, "1.2.0")
        self.assertTrue(info.is_newer)
        self.assertIn("Performance improvements", info.release_notes)
        self.assertEqual(info.asset_name, "ParqBench-Setup-x64.exe")
        self.assertEqual(info.download_url, "https://github.com/downloads/ParqBench-Setup-x64.exe")


class TestUpdaterDialog(unittest.TestCase):

    def test_dialog_with_newer_version(self):
        info = UpdateInfo(
            current_version="1.0.0",
            latest_version="1.2.0",
            is_newer=True,
            release_notes="Awesome new features in v1.2.0",
            download_url="https://example.com/ParqBench-Setup.exe",
            asset_name="ParqBench-Setup.exe",
            html_url="https://github.com/TOXiC-G/ParqBench/releases/tag/v1.2.0",
            asset_size=1024 * 1024 * 20,
        )
        dlg = UpdaterDialog(initial_info=info)
        self.assertFalse(dlg.btn_action.isHidden())
        self.assertEqual(dlg.btn_action.text(), "Download & Install Update")
        self.assertIn("v1.2.0 Available", dlg.lbl_badge.text())
        self.assertIn("Awesome new features", dlg.txt_notes.toPlainText())
        dlg.close()

    def test_dialog_with_up_to_date_version(self):
        info = UpdateInfo(
            current_version="1.0.0",
            latest_version="1.0.0",
            is_newer=False,
            release_notes="No changes",
            download_url=None,
            asset_name=None,
            html_url="https://github.com/TOXiC-G/ParqBench/releases/tag/v1.0.0",
        )
        dlg = UpdaterDialog(initial_info=info)
        self.assertEqual(dlg.lbl_badge.text(), "Up to Date")
        self.assertTrue(dlg.btn_action.isHidden())
        self.assertFalse(dlg.btn_check_again.isHidden())
        dlg.close()


class TestMainWindowUpdateSettings(unittest.TestCase):

    def setUp(self):
        # Temporary settings isolation
        self.settings = QSettings("ParqBench_Test", "ParqBench_Test")

    def tearDown(self):
        self.settings.clear()

    def test_settings_toggle_and_toolbar(self):
        window = MainWindow()
        self.assertIsNotNone(window.act_check_updates_startup)

        # Toggle check on startup
        window._toggle_update_on_startup(False)
        self.assertFalse(window._settings.value("check_updates_on_startup", True, type=bool))
        self.assertFalse(window.act_check_updates_startup.isChecked())

        window._toggle_update_on_startup(True)
        self.assertTrue(window._settings.value("check_updates_on_startup", False, type=bool))
        self.assertTrue(window.act_check_updates_startup.isChecked())

        window.close()

    def test_top_bar_corner_indicator_on_update_found(self):
        window = MainWindow()
        self.assertFalse(window.btn_update_available.isVisible())

        # Simulate update found
        info = UpdateInfo(
            current_version="1.0.0",
            latest_version="1.3.0",
            is_newer=True,
            release_notes="Notes",
            download_url="http://example.com/ParqBench.exe",
            asset_name="ParqBench.exe",
            html_url="http://example.com",
        )
        window._on_silent_check_finished(info, "")

        self.assertFalse(window.btn_update_available.isHidden())
        self.assertIn("v1.3.0", window.btn_update_available.text())
        self.assertTrue(window.lbl_update_status.isHidden())

        window.close()

    def test_top_bar_corner_indicator_when_up_to_date(self):
        window = MainWindow()
        info = UpdateInfo(
            current_version="1.0.0",
            latest_version="1.0.0",
            is_newer=False,
            release_notes="No changes",
            download_url=None,
            asset_name=None,
            html_url=None,
        )
        window._on_silent_check_finished(info, "")

        self.assertTrue(window.btn_update_available.isHidden())
        self.assertIn("Up to date", window.lbl_update_status.text())

        window.close()


if __name__ == "__main__":
    unittest.main()
