"""Regressionstests für die atomaren JSON-Nutzdaten-Writes (_save_data/_load_data).

Hintergrund: Während eines Live-Events schrieben viele nebenläufige Requests in
dieselbe events.json. Mit nicht-atomaren Writes konnte ein Reader eine halb
geschriebene Datei erwischen → _load_data lieferte still [] → der nächste
_save_data schrieb die leere Liste fest = das ganze Event verschwand mitten im
Betrieb. Diese Tests sichern das abgestellte Verhalten ab.
"""
import os
import sys
import tempfile
import threading

import pytest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_APP_PATH = os.path.join(os.path.dirname(CURRENT_DIR), "web_app")
if WEB_APP_PATH not in sys.path:
    sys.path.insert(0, WEB_APP_PATH)

import utils  # noqa: E402


@pytest.fixture()
def fresh_data_dir():
    prev = os.environ.get("AGILITY_DATA_DIR")
    os.environ["AGILITY_DATA_DIR"] = tempfile.mkdtemp()
    try:
        yield os.environ["AGILITY_DATA_DIR"]
    finally:
        if prev is None:
            os.environ.pop("AGILITY_DATA_DIR", None)
        else:
            os.environ["AGILITY_DATA_DIR"] = prev


def test_corrupt_existing_file_raises_instead_of_silent_empty(fresh_data_dir):
    """Eine existierende, aber unlesbare Datei darf NIEMALS still als []
    gelesen werden — sonst schreibt der nächste _save_data den Verlust fest."""
    path = os.path.join(fresh_data_dir, "events.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write('[{"id": "e1", "Bezeichnung": "Jump Into Fall"')  # abgeschnitten
    with pytest.raises(RuntimeError):
        utils._load_data("events.json")


def test_valid_prefix_with_trailing_garbage_raises(fresh_data_dir):
    """Exakt der im Live-Betrieb beobachtete Korruptionsfall: ein VOLLSTÄNDIGES,
    für sich gültiges JSON gefolgt von einem Müll-Schwanz (zwei verschränkte,
    nicht-atomare Writes — der kürzere Write ließ den längeren Alt-Schwanz stehen).
    json.loads meldet hier "Extra data". Das darf NIE still als [] durchgehen,
    sonst schreibt der nächste _save_data genau diesen Verlust fest."""
    path = os.path.join(fresh_data_dir, "events.json")
    good = '[{"id": "e1", "Bezeichnung": "Jump Into Fall", "runs": []}]'
    tail = '{"id": "e0", "Bezeichnung": "alter laengerer Eintrag"}]'  # Rest-Bytes
    with open(path, "w", encoding="utf-8") as f:
        f.write(good + tail)
    with pytest.raises(RuntimeError):
        utils._load_data("events.json")


def test_overwriting_longer_file_with_shorter_leaves_no_tail(fresh_data_dir):
    """Wurzelursache des Müll-Schwanzes: eine große Datei mit einer kleineren
    überschreiben. Ein In-Place-Truncate-Write (open 'w') könnte alte Rest-Bytes
    hinterlassen; os.replace() ersetzt die Datei komplett. Nach dem kleineren
    Save muss die Datei EXAKT die kleinen Daten enthalten — kein Schwanz, und
    erneut sauber ladbar."""
    big = [{"id": str(i), "blob": "x" * 2000} for i in range(50)]
    utils._save_data("events.json", big)
    small = [{"id": "e1", "Bezeichnung": "klein"}]
    utils._save_data("events.json", small)

    path = os.path.join(fresh_data_dir, "events.json")
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    # Keine Rest-Bytes der großen Datei: muss komplett und nur die kleinen Daten sein
    import json as _json
    assert _json.loads(raw) == small
    assert utils._load_data("events.json") == small


def test_missing_file_returns_default(fresh_data_dir):
    assert utils._load_data("events.json") == []
    assert utils._load_data("active_event.json", {}) == {}


def test_empty_file_treated_as_default(fresh_data_dir):
    path = os.path.join(fresh_data_dir, "events.json")
    open(path, "w", encoding="utf-8").close()
    assert utils._load_data("events.json") == []


def test_save_leaves_no_tmp_files(fresh_data_dir):
    utils._save_data("events.json", [{"id": "e1", "Bezeichnung": "X"}])
    leftovers = [n for n in os.listdir(fresh_data_dir) if ".tmp." in n]
    assert leftovers == []
    assert utils._load_data("events.json") == [{"id": "e1", "Bezeichnung": "X"}]


def test_concurrent_read_never_sees_partial_and_event_survives(fresh_data_dir):
    """Viele parallele Writer + Reader auf derselben events.json: Das Event
    darf nie verschwinden und ein Reader darf nie eine leere/partielle Liste
    bekommen (atomare Writes + Lock)."""
    big_event = {"id": "e1", "Bezeichnung": "Jump Into Fall",
                 "runs": [{"id": str(i), "entries": list(range(50))} for i in range(40)]}
    utils._save_data("events.json", [big_event])

    errors = []

    def writer():
        for _ in range(60):
            try:
                events = utils._load_data("events.json")
                # in-place Mini-Änderung, ganze Liste zurückschreiben
                events[0]["runs"][0]["entries"].append(1)
                utils._save_data("events.json", events)
            except Exception as e:  # noqa: BLE001
                errors.append(("writer", repr(e)))
                return

    def reader():
        for _ in range(120):
            try:
                events = utils._load_data("events.json")
                assert events and events[0]["id"] == "e1"
            except Exception as e:  # noqa: BLE001
                errors.append(("reader", repr(e)))
                return

    threads = [threading.Thread(target=writer) for _ in range(4)] + \
              [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], errors
    final = utils._load_data("events.json")
    assert len(final) == 1 and final[0]["id"] == "e1"
