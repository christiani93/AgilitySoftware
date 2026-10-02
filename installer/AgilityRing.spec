# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spec für den Ring-Server (AgilityRing).

WICHTIG: Aus der 32-bit-venv (ring_env) bauen, sonst funktioniert TIMY/pywin32
nicht. Build aus dem Projekt-Root:

    web_app\\ring_env\\Scripts\\activate
    pyinstaller installer\\AgilityRing.spec --noconfirm

Output: dist\\AgilityRing.exe (Single-File, mit Konsole + Tkinter-Launcher)
"""
import os
import sys

block_cipher = None

PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
WEB_APP = os.path.join(PROJECT_ROOT, "web_app")
RING_DIR = os.path.join(WEB_APP, "ring_server")

# In einer venv liegen tkinter/_tkinter/Tcl-Tk nur im Basis-Python. PyInstallers
# Modulgraph durchsucht das Basis-DLLs-Verzeichnis nicht automatisch, wodurch
# _tkinter (und damit tkinter) als "missing" gilt und der Tcl/Tk-Hook nie greift.
# Basis-DLLs + Lib explizit auf den Suchpfad legen, damit der Hook anspringt.
_BASE = sys.base_prefix
EXTRA_PATHEX = [os.path.join(_BASE, "DLLs"), os.path.join(_BASE, "Lib")]

# Der tkinter-Hook bündelt bei venv-Builds _tkinter.pyd + DLLs, findet aber die
# Tcl/Tk-Script-Libraries nicht. Der Runtime-Hook erwartet sie als _tcl_data /
# _tk_data im Bundle, sonst: "FileNotFoundError: Tcl data directory ... not found".
# Darum explizit aus dem Basis-Python mitnehmen.
_TCL = os.path.join(_BASE, "tcl")
datas = []
for _src, _dst in [("tcl8.6", "_tcl_data"), ("tk8.6", "_tk_data"), ("tcl8", "tcl8")]:
    _p = os.path.join(_TCL, _src)
    if os.path.isdir(_p):
        datas.append((_p, _dst))

# Das reine Python-Paket "tkinter" wird vom Modulgraph bei venv-Builds nicht
# gefunden (nur _tkinter als C-Extension kommt über den Hook rein). Darum das
# Paket direkt aus der Basis-Lib mitnehmen, sonst: ModuleNotFoundError 'tkinter'.
_TKPKG = os.path.join(_BASE, "Lib", "tkinter")
if os.path.isdir(_TKPKG):
    datas.append((_TKPKG, "tkinter"))

# App-Icon mitbündeln, damit der Tk-Launcher es zur Laufzeit via iconbitmap setzen
# kann (tkinter uebernimmt das eingebettete EXE-Icon nicht automatisch).
_RING_ICO = os.path.join(PROJECT_ROOT, "assets", "ring.ico")
if os.path.isfile(_RING_ICO):
    datas.append((_RING_ICO, "."))

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
    "tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
    "_tkinter",
]

a = Analysis(
    [os.path.join(RING_DIR, "ring_launcher.py")],
    pathex=[RING_DIR, WEB_APP, PROJECT_ROOT] + EXTRA_PATHEX,
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
    icon=_RING_ICO if os.path.isfile(_RING_ICO) else None,
)
