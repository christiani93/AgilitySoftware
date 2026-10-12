"""Tests fuer das In-Process-Backup (data_backup.backup_once).

Zweite Verteidigungslinie nach dem Atomic-Write-Fix: sichert events.json/
active_event.json rotierend. Diese Tests sichern Kernverhalten ab: gueltige
Dateien werden gesichert, unveraenderte nicht erneut, korrupte nie propagiert,
und die Rotation behaelt nur die juengsten Staende.
"""
import os
import sys
import tempfile

import pytest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_APP_PATH = os.path.join(os.path.dirname(CURRENT_DIR), "web_app")
if WEB_APP_PATH not in sys.path:
    sys.path.insert(0, WEB_APP_PATH)

import data_backup  # noqa: E402


@pytest.fixture()
def dirs():
    data_dir = tempfile.mkdtemp()
    backup_dir = tempfile.mkdtemp()
    yield data_dir, backup_dir


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _backups_for(backup_dir, stem):
    return sorted(n for n in os.listdir(backup_dir) if n.startswith(f"{stem}_"))


def test_valid_file_is_backed_up(dirs):
    data_dir, backup_dir = dirs
    _write(os.path.join(data_dir, "events.json"), '[{"id": "e1"}]')
    last = {}
    data_backup.backup_once(data_dir, backup_dir, ["events.json"], 24, last)
    copies = _backups_for(backup_dir, "events")
    assert len(copies) == 1
    with open(os.path.join(backup_dir, copies[0]), encoding="utf-8") as f:
        assert f.read() == '[{"id": "e1"}]'


def test_unchanged_file_not_backed_up_twice(dirs):
    data_dir, backup_dir = dirs
    _write(os.path.join(data_dir, "events.json"), '[{"id": "e1"}]')
    last = {}
    data_backup.backup_once(data_dir, backup_dir, ["events.json"], 24, last)
    data_backup.backup_once(data_dir, backup_dir, ["events.json"], 24, last)
    assert len(_backups_for(backup_dir, "events")) == 1


def test_changed_file_creates_new_backup(dirs):
    data_dir, backup_dir = dirs
    path = os.path.join(data_dir, "events.json")
    last = {}
    _write(path, '[{"id": "e1"}]')
    data_backup.backup_once(data_dir, backup_dir, ["events.json"], 24, last)
    # Dateiname hat Sekunden-Granularitaet -> Zeitstempel erzwingen, damit zwei
    # Staende im selben Testlauf nicht denselben Namen bekommen.
    import datetime as _dt
    real = data_backup.datetime

    class _FakeDt:
        @staticmethod
        def now():
            return real.now() + _dt.timedelta(seconds=5)

    data_backup.datetime = _FakeDt
    try:
        _write(path, '[{"id": "e1"}, {"id": "e2"}]')
        data_backup.backup_once(data_dir, backup_dir, ["events.json"], 24, last)
    finally:
        data_backup.datetime = real
    assert len(_backups_for(backup_dir, "events")) == 2


def test_corrupt_file_not_propagated(dirs):
    data_dir, backup_dir = dirs
    _write(os.path.join(data_dir, "events.json"), '[{"id": "e1"')  # abgeschnitten
    last = {}
    data_backup.backup_once(data_dir, backup_dir, ["events.json"], 24, last)
    assert _backups_for(backup_dir, "events") == []
    assert "events.json" not in last


def test_empty_file_skipped(dirs):
    data_dir, backup_dir = dirs
    open(os.path.join(data_dir, "events.json"), "w").close()
    last = {}
    data_backup.backup_once(data_dir, backup_dir, ["events.json"], 24, last)
    assert _backups_for(backup_dir, "events") == []


def test_missing_file_skipped(dirs):
    data_dir, backup_dir = dirs
    last = {}
    data_backup.backup_once(data_dir, backup_dir, ["events.json"], 24, last)
    assert _backups_for(backup_dir, "events") == []


def test_prune_keeps_only_newest(dirs):
    data_dir, backup_dir = dirs
    # 5 vorhandene Staende simulieren, keep=3 -> die 2 aeltesten werden entfernt
    for i in range(5):
        _write(os.path.join(backup_dir, f"events_2026010{i}_120000.json"), "[]")
    data_backup._prune(backup_dir, "events.json", 3)
    remaining = _backups_for(backup_dir, "events")
    assert remaining == [
        "events_20260102_120000.json",
        "events_20260103_120000.json",
        "events_20260104_120000.json",
    ]


def test_atomic_copy_leaves_no_tmp(dirs):
    _, backup_dir = dirs
    dest = os.path.join(backup_dir, "events_x.json")
    data_backup._atomic_copy(b"[]", dest)
    assert os.path.exists(dest)
    assert [n for n in os.listdir(backup_dir) if ".tmp." in n] == []
