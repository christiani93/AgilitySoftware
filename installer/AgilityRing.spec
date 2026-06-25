# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spec für den Ring-Server (AgilityRing).

WICHTIG: Aus der 32-bit-venv (ring_env) bauen, sonst funktioniert TIMY/pywin32
nicht. Build aus dem Projekt-Root:

    web_app\\ring_env\\Scripts\\activate
    pyinstaller installer\\AgilityRing.spec --noconfirm

Output: dist\\AgilityRing.exe (Single-File, mit Konsole + Tkinter-Launcher)
"""
import os

block_cipher = None

PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
WEB_APP = os.path.join(PROJECT_ROOT, "web_app")
RING_DIR = os.path.join(WEB_APP, "ring_server")

datas = []

hiddenimports = [
    "engineio.async_drivers.threading",
    "engineio.async_threading",
    "flask_socketio",
    "ring_server",
    "ring_dashboard",
    "updater",
    "pythoncom",
    "win32com",
    "win32com.client",
    "pywintypes",
]

a = Analysis(
    [os.path.join(RING_DIR, "ring_launcher.py")],
    pathex=[RING_DIR, WEB_APP, PROJECT_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="AgilityRing",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # Konsole versteckt – Status zeigt das Tk-Dashboard
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
