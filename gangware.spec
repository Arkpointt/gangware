# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

# Get the project root directory
PROJECT_ROOT = Path.cwd()

block_cipher = None

a = Analysis(
    ['src/gangware/main.py'],
    pathex=[str(PROJECT_ROOT), str(PROJECT_ROOT / 'src')],
    binaries=[],
    datas=[
        # Include all assets
        ('assets', 'assets'),
        # Include config files
        ('config', 'config'),
        # Include any additional data files
        ('*.md', '.'),
        ('requirements.txt', '.'),
        # Include packaged stylesheet for overlay (used in frozen runtime)
        ('src/gangware/gui/theme.qss', 'gangware/gui'),
    ],
    hiddenimports=[
        # PyQt6 modules
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        # OpenCV
        'cv2',
        # NumPy
        'numpy',
        # MSS for screenshots
        'mss',
        # Input control
        'pydirectinput',
        # Standard library modules that might be needed
        'configparser',
        'logging',
        'threading',
        'pathlib',
        'time',
        'os',
        'sys',
        # Gangware modules
        'gangware',
        'gangware.core',
        'gangware.controllers',
        'gangware.gui',
        'gangware.macros',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary modules to reduce size
        'tkinter',
        'unittest',
        'test',
        'distutils',
        'setuptools',
        'pip',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Gangware',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to True if you want console output for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if Path('assets/icon.ico').exists() else None,
    version_file=None,
)
