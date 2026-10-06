"""Pure-Python-Tests für den EventExport-Import (Portal → Software).

Deckt die Stelle ab, die vorher stillschweigend 0 Einträge erzeugte: Der
Portal-Export inlint Hund/Hundeführer nicht, sondern referenziert sie per
external_id (Daten liegen in entities, Key "persons"/"dogs"). Zusätzlich wird
der Verein (club_name → Vereinsnummer am Handler) geprüft.
"""
import os
import sys
import tempfile

import pytest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_APP_PATH = os.path.join(os.path.dirname(CURRENT_DIR), "web_app")
if WEB_APP_PATH not in sys.path:
    sys.path.insert(0, WEB_APP_PATH)

import blueprints.routes_events as R  # noqa: E402
import utils  # noqa: E402


@pytest.fixture()
def fresh_data_dir():
    """Isoliertes Temp-Datenverzeichnis; stellt AGILITY_DATA_DIR danach wieder
    her, damit nachfolgende Tests nicht auf das leere Temp-Dir zeigen."""
    prev = os.environ.get("AGILITY_DATA_DIR")
    os.environ["AGILITY_DATA_DIR"] = tempfile.mkdtemp()
    utils._save_data("dogs.json", [])
    utils._save_data("handlers.json", [])
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("AGILITY_DATA_DIR", None)
        else:
            os.environ["AGILITY_DATA_DIR"] = prev


def _portal_payload():
    entities = {
        "persons": [
            {"external_id": "P1", "first_name": "Christiane", "last_name": "Broennimann", "email": None},
            {"external_id": "P2", "first_name": "Claire", "last_name": "Arola", "email": None},
        ],
        "dogs": [
            {"external_id": "D1", "name": "Mac", "license_no": "15333", "license_kind": "CH"},
            {"external_id": "D2", "name": "Fate", "license_no": "FRA-105002", "license_kind": "FOREIGN"},
        ],
    }
    regs = [
        {"external_id": "R1", "dog_external_id": "D1", "handler_person_external_id": "P1",
         "category_code": "Large", "class_level": 1, "club_name": "512"},
        {"external_id": "R2", "dog_external_id": "D2", "handler_person_external_id": "P2",
         "category_code": "Large", "class_level": 1, "club_name": "--- AUSLAND ---"},
    ]
    return entities, regs


def test_eventexport_resolves_dog_handler_and_club_by_external_id(fresh_data_dir):
    entities, regs = _portal_payload()
    event = {"id": "ev1", "runs": []}

    info = R._apply_eventexport_registrations(event, regs, entities)

    # Vorher: 0 (Hund/HF/Lizenz nur per external_id referenziert, nicht inline)
    assert info["entries_added"] == 2
    entries = {e["Lizenznummer"]: e for run in event["runs"] for e in run["entries"]}
    assert entries["15333"]["Hundename"] == "Mac"
    assert entries["15333"]["Hundefuehrer"] == "Christiane Broennimann"
    assert entries["15333"]["Kategorie"] == "Large"
    assert entries["15333"]["Klasse"] == "1"

    # Verein landet als Vereinsnummer am Handler (clubs.json löst später den Namen auf)
    handlers = {h.get("Nachname"): h for h in utils._load_data("handlers.json")}
    assert handlers["Broennimann"]["Vereinsnummer"] == "512"
    assert handlers["Arola"]["Vereinsnummer"] == "--- AUSLAND ---"


def test_eventexport_persons_key_is_recognized_as_handlers(fresh_data_dir):
    """Portal nutzt den entities-Key 'persons' (nicht 'handlers'/'people')."""
    entities, regs = _portal_payload()
    handler_map = R._merge_eventexport_handlers([], entities)
    assert set(handler_map.keys()) == {"P1", "P2"}
    assert handler_map["P1"]["Vorname"] == "Christiane"
