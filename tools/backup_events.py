"""backup_events.py — externes 5-Minuten-Backup der AgilitySoftware-Nutzdaten.

Sofort-Sicherheitsnetz fuer den Event-Tag: ein separater Prozess, der die
kritischen JSON-Dateien (events.json, active_event.json) regelmaessig rotierend
wegsichert. Null Risiko fuer den laufenden Hauptserver — es wird nur GELESEN.
Da der Hauptserver seit dem Atomic-Write-Fix (utils._save_data -> os.replace)
immer ganz-oder-gar-nicht schreibt, sieht dieser Leser nie eine halbe Datei.

Spaeter wird dasselbe Verhalten in die Software selbst integriert
(In-Process-Timer-Thread). Bis dahin: dieses Skript neben dem Server laufen lassen.

Nur Standardbibliothek, keine Abhaengigkeiten. Beispiel:

    python -I tools/backup_events.py
    python -I tools/backup_events.py --data-dir dist/data --interval 300 --keep 24
    python -I tools/backup_events.py --once        # einmal sichern und beenden

Standardwerte:
    --data-dir    web_app/data   (DEV-Server; fuer die EXE: dist/data)
    --backup-dir  C:/Users/chris/AgilityBackups/auto
    --interval    300 Sekunden (5 Minuten)
    --keep        24 Staende je Datei (= 2 Stunden bei 5-Min-Takt)
    --files       events.json,active_event.json
"""
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime


def _log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_valid_json(data: bytes) -> bool:
    try:
        json.loads(data.decode("utf-8"))
        return True
    except (ValueError, UnicodeDecodeError):
        return False


def _atomic_copy(src_bytes: bytes, dest: str) -> None:
    """Schreibt das Backup atomar (tmp + os.replace), damit ein paralleler
    Leser des Backups nie eine halbe Datei sieht."""
    tmp = f"{dest}.tmp.{os.getpid()}.{int(time.time()*1000)}"
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
    """Behaelt nur die `keep` neuesten Backups fuer eine Basis-Datei (z.B.
    events) — Dateiname-Muster <base>_YYYYmmdd_HHMMSS.json."""
    stem = os.path.splitext(base)[0]
    prefix = f"{stem}_"
    suffix = os.path.splitext(base)[1] or ".json"
    matches = sorted(
        n for n in os.listdir(backup_dir)
        if n.startswith(prefix) and n.endswith(suffix)
    )
    for old in matches[:-keep] if keep > 0 else []:
        try:
            os.remove(os.path.join(backup_dir, old))
        except OSError:
            pass


def backup_once(data_dir: str, backup_dir: str, files, keep: int, last_hashes: dict) -> None:
    os.makedirs(backup_dir, exist_ok=True)
    for base in files:
        src = os.path.join(data_dir, base)
        if not os.path.exists(src):
            continue
        try:
            with open(src, "rb") as f:
                content = f.read()
        except OSError as e:
            _log(f"WARN {base}: lesen fehlgeschlagen ({e}) — uebersprungen")
            continue
        if content.strip() == b"":
            continue  # leere/frisch initialisierte Datei nicht sichern
        if not _is_valid_json(content):
            # Korrupte Datei NICHT ins Backup propagieren — nur warnen.
            _log(f"WARN {base}: aktuell kein gueltiges JSON — Backup uebersprungen")
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
        _log(f"OK  {base} -> {os.path.basename(dest)} ({len(content)} bytes)")


def main(argv=None):
    p = argparse.ArgumentParser(description="Rotierendes 5-Min-Backup der AgilitySoftware-Nutzdaten.")
    p.add_argument("--data-dir", default=os.path.join("web_app", "data"))
    p.add_argument("--backup-dir", default=r"C:/Users/chris/AgilityBackups/auto")
    p.add_argument("--interval", type=int, default=300, help="Sekunden zwischen Backups")
    p.add_argument("--keep", type=int, default=24, help="Anzahl Staende je Datei")
    p.add_argument("--files", default="events.json,active_event.json",
                   help="kommagetrennte Dateinamen im data-Dir")
    p.add_argument("--once", action="store_true", help="einmal sichern und beenden")
    args = p.parse_args(argv)

    files = [x.strip() for x in args.files.split(",") if x.strip()]
    data_dir = os.path.abspath(args.data_dir)
    backup_dir = os.path.abspath(args.backup_dir)

    if not os.path.isdir(data_dir):
        _log(f"FEHLER: data-Dir existiert nicht: {data_dir}")
        return 2

    _log(f"Backup gestartet: {data_dir} -> {backup_dir}")
    _log(f"Dateien={files} interval={args.interval}s keep={args.keep} "
         f"{'(einmalig)' if args.once else ''}")

    last_hashes: dict = {}
    try:
        backup_once(data_dir, backup_dir, files, args.keep, last_hashes)
        if args.once:
            return 0
        while True:
            time.sleep(args.interval)
            backup_once(data_dir, backup_dir, files, args.keep, last_hashes)
    except KeyboardInterrupt:
        _log("beendet (Ctrl+C)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
