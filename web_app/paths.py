"""Pfad-Helfer für Dev-Modus und PyInstaller-Bundle.

Bei PyInstaller-``--onefile``-Builds werden mitgebündelte Ressourcen
(Templates, Static, Übersetzungen) in einen Temp-Ordner unter
``sys._MEIPASS`` entpackt. Schreibbare Nutzdaten (Events, Settings)
müssen aber persistent neben der EXE liegen.

Dieses Modul kapselt das, damit der restliche Code identisch in Dev
und in der gepackten EXE läuft.
"""
from __future__ import annotations

import os
import sys


def is_frozen() -> bool:
    """True, wenn der Code in einem PyInstaller-Bundle läuft."""
    return getattr(sys, "frozen", False)


def bundle_dir() -> str:
    """Ordner für read-only Ressourcen (Templates, Static, Translations).

    - Dev: das ``web_app/``-Verzeichnis (Ordner dieser Datei).
    - Frozen: ``sys._MEIPASS``-Temp-Ordner mit den eingebetteten Dateien.
    """
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def app_dir() -> str:
    """Ordner der EXE (frozen) bzw. ``web_app/`` (dev).

    Hier liegen ``data/``, Config-Files, Logs etc.
    """
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def data_dir() -> str:
    """Verzeichnis für schreibbare Nutzdaten (Events, Settings, etc.).

    Override via Env ``AGILITY_DATA_DIR`` (z.B. NAS-Share).
    Default: ``<app_dir>/data``.
    """
    override = os.environ.get("AGILITY_DATA_DIR")
    if override:
        return override
    return os.path.join(app_dir(), "data")


def data_path(*parts: str) -> str:
    """Pfad innerhalb von ``data_dir()`` (erstellt das Verzeichnis bei Bedarf)."""
    d = data_dir()
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, *parts)


def resource_path(*parts: str) -> str:
    """Pfad innerhalb des Bundle-Verzeichnisses (read-only Resources)."""
    return os.path.join(bundle_dir(), *parts)
