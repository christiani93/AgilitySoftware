# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spec für den Hauptserver (AgilitySoftware).

Build aus dem Projekt-Root:
    flask_env\\Scripts\\activate
    pyinstaller installer\\AgilitySoftware.spec --noconfirm

Output: dist\\AgilitySoftware.exe (Single-File, mit Konsole)
"""
import os

block_cipher = None

# Projekt-Wurzel: installer/ liegt eine Ebene unter dem Root.
PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
WEB_APP = os.path.join(PROJECT_ROOT, "web_app")

datas = [
    (os.path.join(WEB_APP, "templates"), "templates"),
    (os.path.join(WEB_APP, "static"), "static"),
    (os.path.join(WEB_APP, "translations"), "translations"),
    (os.path.join(WEB_APP, "babel.cfg"), "."),
]

hiddenimports = [
    "engineio.async_drivers.threading",
    "engineio.async_threading",
    "flask_socketio",
    "flask_babel",
    "blueprints.routes_events",
    "blueprints.routes_master_data",
    "blueprints.routes_print",
    "blueprints.routes_live",
    "blueprints.routes_debug",
    "blueprints.routes_sm",
    "blueprints.routes_skbs_sm",
    "live.live_state",
    "live.ring_state",
    "planner.schedule_planner",
    "webview",
    "webview.platforms.edgechromium",
    "clr_loader",
    "pythonnet",
]

a = Analysis(
    [os.path.join(WEB_APP, "app.py")],
    pathex=[WEB_APP, PROJECT_ROOT],
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
    name="AgilitySoftware",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # Konsole versteckt – LAN-IP wird im Web-UI angezeigt
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
