"""In-Process-Backup der kritischen Nutzdaten-JSONs.

Zweite Verteidigungslinie nach dem Atomic-Write-Fix (``utils._save_data`` ->
``os.replace``): ein Daemon-Thread sichert ``events.json`` und
``active_event.json`` alle N Sekunden rotierend weg. So laesst sich ein
unerwarteter Datenfehler (im schlimmsten Fall ein last-writer-wins) auf einen
Stand von hoechstens N Sekunden vorher zurueckrollen.

Anders als ``tools/backup_events.py`` (externer Prozess, Sofort-Sicherheitsnetz)
laeuft dieses Modul MIT der Software und kommt in die EXE.

WICHTIG: Gelesen wird unter ``utils._DATA_LOCK``. Auf Windows wuerde ein
offener Lese-Handle den atomaren ``os.replace`` eines parallelen ``_save_data``
mit PermissionError scheitern lassen. Unter demselben Lock, den auch
``_load_data``/``_save_data`` halten, gibt es keine Ueberlappung — das Backup
baut also keine neue Fehlerquelle in den Live-Server ein.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime

try:  # Dev-Server importiert web_app-Module top-level, Tests ebenso
    from utils import _DATA_LOCK
    from paths import app_dir, data_dir
except ImportError:  # pragma: no cover - alternativer Importpfad
    from web_app.utils import _DATA_LOCK
    from web_app.paths import app_dir, data_dir

DEFAULT_FILES = ("events.json", "active_event.json")
DEFAULT_INTERVAL = 300  # Sekunden (5 Minuten)
DEFAULT_KEEP = 24       # Staende je Datei (= 2 Stunden bei 5-Min-Takt)

_thread_lock = threading.Lock()
_thread_started = False


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_valid_json(data: bytes) -> bool:
    try:
        json.loads(data.decode("utf-8"))
        return True
    except (ValueError, UnicodeDecodeError):
        return False


def _read_locked(path: str) -> bytes | None:
    """Liest die Datei unter ``_DATA_LOCK`` (konsistenter Snapshot, keine
    Kollision mit einem laufenden ``os.replace``-Write). ``None`` wenn die Datei
    fehlt oder nicht lesbar ist."""
    with _DATA_LOCK:
        if not os.path.exists(path):
            return None
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            return None


def _atomic_copy(src_bytes: bytes, dest: str) -> None:
    """Schreibt das Backup atomar (tmp + os.replace), damit ein paralleler
    Leser des Backups nie eine halbe Datei sieht."""
    tmp = f"{dest}.tmp.{os.getpid()}.{int(time.time() * 1000)}"
    try:
        with open(tmp, "wb") as f:
            f.write(src_bytes)
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _prune(backup_dir: str, base: str, keep: int) -> None:
    """Behaelt nur die ``keep`` neuesten Backups fuer eine Basis-Datei
    (Dateiname-Muster ``<stem>_YYYYmmdd_HHMMSS<ext>``)."""
    if keep <= 0:
        return
    stem = os.path.splitext(base)[0]
    prefix = f"{stem}_"
    suffix = os.path.splitext(base)[1] or ".json"
    try:
        names = os.listdir(backup_dir)
    except OSError:
        return
    matches = sorted(n for n in names if n.startswith(prefix) and n.endswith(suffix))
    for old in matches[:-keep]:
        try:
            os.remove(os.path.join(backup_dir, old))
        except OSError:
            pass


def backup_once(data_dir_path: str, backup_dir: str, files, keep: int, last_hashes: dict) -> None:
    """Sichert alle ``files`` aus ``data_dir_path`` einmal nach ``backup_dir``.

    Ueberspringt leere, korrupte (kein gueltiges JSON) und seit dem letzten Lauf
    unveraenderte Dateien. ``last_hashes`` wird in-place gepflegt."""
    os.makedirs(backup_dir, exist_ok=True)
    for base in files:
        src = os.path.join(data_dir_path, base)
        content = _read_locked(src)
        if content is None:
            continue
        if content.strip() == b"":
            continue  # leere/frisch initialisierte Datei nicht sichern
        if not _is_valid_json(content):
            # Korrupte Datei NICHT ins Backup propagieren.
            continue
        digest = _sha(content)
        if last_hashes.get(base) == digest:
            continue  # unveraendert seit letztem Backup -> keine Dublette
        stem = os.path.splitext(base)[0]
        ext = os.path.splitext(base)[1] or ".json"
        dest = os.path.join(backup_dir, f"{stem}_{datetime.now():%Y%m%d_%H%M%S}{ext}")
        _atomic_copy(content, dest)
        last_hashes[base] = digest
        _prune(backup_dir, base, keep)


def _default_backup_dir() -> str:
    override = os.environ.get("AGILITY_BACKUP_DIR")
    if override:
        return override
    return os.path.join(app_dir(), "backups")


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, "").strip())
        return value if value > 0 else default
    except (ValueError, AttributeError):
        return default


def _backup_loop(data_dir_path: str, backup_dir: str, files, interval: int, keep: int) -> None:
    last_hashes: dict = {}
    # Sofort einmal sichern (fester Ausgangsstand), danach im Intervall.
    try:
        backup_once(data_dir_path, backup_dir, files, keep, last_hashes)
    except Exception:  # noqa: BLE001 - ein Backup-Fehler darf den Server nie stoppen
        pass
    while True:
        time.sleep(interval)
        try:
            backup_once(data_dir_path, backup_dir, files, keep, last_hashes)
        except Exception:  # noqa: BLE001
            pass


def start_backup_thread(files=DEFAULT_FILES, interval: int | None = None,
                        keep: int | None = None, backup_dir: str | None = None) -> bool:
    """Startet den Backup-Daemon-Thread. Idempotent — ein zweiter Aufruf im
    selben Prozess ist ein No-Op. Gibt True zurueck, wenn der Thread (neu)
    gestartet wurde."""
    global _thread_started
    with _thread_lock:
        if _thread_started:
            return False
        _thread_started = True

    data_dir_path = data_dir()
    backup_dir = backup_dir or _default_backup_dir()
    interval = interval if interval is not None else _int_env("AGILITY_BACKUP_INTERVAL", DEFAULT_INTERVAL)
    keep = keep if keep is not None else _int_env("AGILITY_BACKUP_KEEP", DEFAULT_KEEP)

    t = threading.Thread(
        target=_backup_loop,
        args=(data_dir_path, backup_dir, list(files), interval, keep),
        name="data-backup",
        daemon=True,
    )
    t.start()
    return True
