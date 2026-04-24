# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for OVMS Manager.

Bundles the GUI app and lightweight dependencies.
Heavy packages (openvino, OVMS binary, models) are intentionally excluded —
the Setup tab handles those at first run.
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_dir = Path(SPECPATH)

# customtkinter needs its assets (themes, images)
ctk_datas = collect_data_files('customtkinter')

a = Analysis(
    [str(project_dir / 'main.py')],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[
        (str(project_dir / 'assets'), 'assets'),
        (str(project_dir / 'app'),    'app'),
        *ctk_datas,
    ],
    hiddenimports=[
        'customtkinter',
        'darkdetect',
        'PIL._tkinter_finder',
        'pystray',
        'pystray._win32',
        'httpx',
        'duckduckgo_search',
        'app.config',
        'app.gui',
        'app.server',
        'app.models',
        'app.chat',
        'app.tools',
        'app.guide',
        'app.about',
        'app.setup_tab',
        'app.installer',
        'app.log_viewer',
        'app.icon',
        'winreg',
    ],
    excludes=[
        # Exclude heavy AI/ML packages — not bundled, installed separately
        'openvino', 'openvino_genai', 'openvino_tokenizers',
        'torch', 'torchvision', 'tensorflow',
        'transformers', 'tokenizers', 'safetensors',
        'IPython', 'jupyter', 'notebook',
        'matplotlib', 'scipy', 'sklearn',
        'test', 'unittest',
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OVMS Manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                        # no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_dir / 'assets' / 'icon.ico'),
    version_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OVMS Manager',
)
