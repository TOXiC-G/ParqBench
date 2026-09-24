"""
ParqBench Software Update Engine
Handles GitHub Releases API querying, version parsing, background downloads,
and launching non-admin updates.
"""
from __future__ import annotations

import os
import sys
import json
import tempfile
import subprocess
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional, Tuple
import re

from PySide6.QtCore import QObject, Signal, QThread
from src import __version__, __app_name__

GITHUB_REPO = "TOXiC-G/ParqBench"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
USER_AGENT = f"ParqBench-Updater/{__version__}"


def parse_semver(v: str) -> Tuple[int, ...]:
    """Parse version string into comparable tuple of ints."""
    clean = re.sub(r"^[^\d]*", "", v.strip())
    parts = re.findall(r"\d+", clean)
    return tuple(map(int, parts)) if parts else (0,)


def is_version_newer(latest: str, current: str = __version__) -> bool:
    """Return True if latest is strictly newer than current version."""
    try:
        from packaging.version import parse
        return parse(latest) > parse(current)
    except Exception:
        return parse_semver(latest) > parse_semver(current)


@dataclass
class UpdateInfo:
    current_version: str
    latest_version: str
    is_newer: bool
    release_notes: str
    download_url: Optional[str]
    asset_name: Optional[str]
    html_url: Optional[str]
    asset_size: int = 0


def fetch_latest_release(repo: str = GITHUB_REPO, timeout: int = 8) -> UpdateInfo:
    """Query GitHub Releases API for the latest release."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github.v3+json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError(f"No releases found yet for repository '{repo}'.")
        raise RuntimeError(f"GitHub API Error: {e.code} {e.reason}")
    except Exception as e:
        raise RuntimeError(f"Network error checking for updates: {str(e)}")

    tag_name = data.get("tag_name", "").lstrip("v")
    notes = data.get("body", "") or "No release notes provided."
    html_url = data.get("html_url", "")

    # Look for Windows executable installer or portable zip in assets
    download_url = None
    asset_name = None
    asset_size = 0

    assets = data.get("assets", [])
    # Preference: .exe installer > portable .zip > any Windows asset
    for a in assets:
        name = a.get("name", "").lower()
        if name.endswith(".exe") and "setup" in name:
            download_url = a.get("browser_download_url")
            asset_name = a.get("name")
            asset_size = a.get("size", 0)
            break

    if not download_url:
        for a in assets:
            name = a.get("name", "").lower()
            if name.endswith(".exe") or name.endswith(".zip"):
                download_url = a.get("browser_download_url")
                asset_name = a.get("name")
                asset_size = a.get("size", 0)
                break

    is_newer = is_version_newer(tag_name, __version__)

    return UpdateInfo(
        current_version=__version__,
        latest_version=tag_name,
        is_newer=is_newer,
        release_notes=notes,
        download_url=download_url,
        asset_name=asset_name,
        html_url=html_url,
        asset_size=asset_size,
    )


class UpdateCheckWorker(QObject):
    """Runs release check in background thread."""
    check_finished = Signal(object, str)  # (UpdateInfo or None, error_message)

    def __init__(self, repo: str = GITHUB_REPO):
        super().__init__()
        self.repo = repo

    def run(self):
        try:
            info = fetch_latest_release(self.repo)
            self.check_finished.emit(info, "")
        except Exception as ex:
            self.check_finished.emit(None, str(ex))


class UpdateDownloadWorker(QObject):
    """Downloads update asset chunk by chunk with progress."""
    progress = Signal(int, int, float)  # (downloaded_bytes, total_bytes, percent)
    download_finished = Signal(str)     # (local_file_path)
    download_failed = Signal(str)       # (error_message)

    def __init__(self, download_url: str, asset_name: str):
        super().__init__()
        self.download_url = download_url
        self.asset_name = asset_name
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            dest_dir = os.path.join(tempfile.gettempdir(), "ParqBench_Update")
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, self.asset_name)

            req = urllib.request.Request(
                self.download_url,
                headers={"User-Agent": USER_AGENT},
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0
                chunk_size = 64 * 1024

                with open(dest_path, "wb") as f:
                    while not self._cancelled:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        pct = (downloaded / total_size * 100) if total_size > 0 else 0.0
                        self.progress.emit(downloaded, total_size, pct)

            if self._cancelled:
                self.download_failed.emit("Download cancelled.")
                return

            self.download_finished.emit(dest_path)

        except Exception as ex:
            self.download_failed.emit(str(ex))


def launch_installer_and_exit(installer_path: str):
    """Launch downloaded installer in non-admin user mode and exit ParqBench."""
    if not os.path.exists(installer_path):
        raise FileNotFoundError(f"Installer not found: {installer_path}")

    # If it's an executable installer
    if installer_path.lower().endswith(".exe"):
        # Launch without elevating, current user mode
        subprocess.Popen([installer_path], shell=False)
        sys.exit(0)
    elif installer_path.lower().endswith(".zip"):
        # Open explorer to the downloaded zip
        subprocess.Popen(f'explorer /select,"{installer_path}"', shell=True)
