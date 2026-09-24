# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None

repo_root = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(repo_root, 'assets'), 'assets'),
]

# Include sample data for user testing if desired
if os.path.exists(os.path.join(repo_root, 'sample_data')):
    datas.append((os.path.join(repo_root, 'sample_data'), 'sample_data'))

hiddenimports = [
    'duckdb',
    'pyarrow',
    'pyarrow.parquet',
    'pyarrow.dataset',
    'pandas',
    'openpyxl',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
]

a = Analysis(
    ['main.py'],
    pathex=[repo_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'torch', 'transformers'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ParqBench',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(repo_root, 'assets', 'icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ParqBench',
)
