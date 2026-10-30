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
            {"external_id": "P2", "first_name": "Claire", "last_name": "Arola", "email": None,
             "fr_licence": "L-98765", "fr_club": "CC Lyon", "fr_regionale": "Rhône-Alpes"},
        ],
        "dogs": [
            {"external_id": "D1", "name": "Mac", "license_no": "15333", "license_kind": "CH",
             "breed": "Border Collie"},
            {"external_id": "D2", "name": "Fate", "license_no": "FRA-105002", "license_kind": "FOREIGN",
             "breed": "Sheltie", "fapac": "D-12345", "sexe": "F"},
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

    # Rasse (Stufe 2) wird vom Portal-Export auf den Hund übernommen
    saved_dogs = {d.get("Lizenznummer"): d for d in utils._load_data("dogs.json")}
    assert saved_dogs["15333"]["Rasse"] == "Border Collie"
    assert saved_dogs["FRA-105002"]["Rasse"] == "Sheltie"


def test_eventexport_persons_key_is_recognized_as_handlers(fresh_data_dir):
    """Portal nutzt den entities-Key 'persons' (nicht 'handlers'/'people')."""
    entities, regs = _portal_payload()
    handler_map = R._merge_eventexport_handlers([], entities)
    assert set(handler_map.keys()) == {"P1", "P2"}
    assert handler_map["P1"]["Vorname"] == "Christiane"


def _tunnel_payload():
    persons = [{"external_id": f"P{i}", "first_name": "V", "last_name": f"N{i}"} for i in range(1, 6)]
    dogs = [{"external_id": f"D{i}", "name": f"Dog{i}", "license_no": str(100 + i),
             "license_kind": "CH"} for i in range(1, 6)]
    regs = [
        {"external_id": "R1", "dog_external_id": "D1", "handler_person_external_id": "P1",
         "discipline": "Tunnellauf", "category_code": "Large", "class_level": 1},
        {"external_id": "R2", "dog_external_id": "D2", "handler_person_external_id": "P2",
         "discipline": "Tunnellauf", "category_code": "Large", "class_level": 2},
        {"external_id": "R3", "dog_external_id": "D3", "handler_person_external_id": "P3",
         "discipline": "Tunnellauf", "category_code": "Large", "class_level": 3},
        {"external_id": "R4", "dog_external_id": "D4", "handler_person_external_id": "P4",
         "discipline": "Tunnellauf", "category_code": "Small", "class_level": 3},
        {"external_id": "R5", "dog_external_id": "D5", "handler_person_external_id": "P5",
         "discipline": "Tunnellauf", "category_code": "Large", "class_level": 1},
    ]
    return {"persons": persons, "dogs": dogs}, regs


def test_tunnellauf_grouped_per_category_not_per_class(fresh_data_dir):
    """HCS-Tunnellauf: EIN Lauf pro Kategorie (alle Klassen zusammen), NICHT pro
    Klasse. Die Einzel-Klasse jedes Hundes bleibt am Entry erhalten."""
    entities, regs = _tunnel_payload()
    event = {"id": "ev1", "runs": []}
    R._apply_eventexport_registrations(event, regs, entities)
    runs = event["runs"]

    tunnel_large = [r for r in runs if r["laufart"] == "Tunnellauf" and r["kategorie"] == "Large"]
    assert len(tunnel_large) == 1, "Large-Tunnellauf muss EIN Lauf sein, nicht pro Klasse"
    assert len(tunnel_large[0]["entries"]) == 4  # Klassen 1,2,3 + zweiter Kl.1-Hund
    assert tunnel_large[0]["klasse"] == ""
    # Einzel-Klassen am Entry erhalten
    assert {str(e["Klasse"]) for e in tunnel_large[0]["entries"]} == {"1", "2", "3"}
    # Andere Kategorie bleibt eigener Lauf
    assert len([r for r in runs if r["laufart"] == "Tunnellauf" and r["kategorie"] == "Small"]) == 1


def test_agility_still_grouped_per_class(fresh_data_dir):
    """Regression: Agility/Jumping bleiben WEITERHIN pro Klasse getrennt."""
    entities = {
        "persons": [{"external_id": "P1", "first_name": "V", "last_name": "A"},
                    {"external_id": "P2", "first_name": "V", "last_name": "B"}],
        "dogs": [{"external_id": "D1", "name": "a", "license_no": "201", "license_kind": "CH"},
                 {"external_id": "D2", "name": "b", "license_no": "202", "license_kind": "CH"}],
    }
    regs = [
        {"external_id": "R1", "dog_external_id": "D1", "handler_person_external_id": "P1",
         "discipline": "Agility", "category_code": "Large", "class_level": 1},
        {"external_id": "R2", "dog_external_id": "D2", "handler_person_external_id": "P2",
         "discipline": "Agility", "category_code": "Large", "class_level": 2},
    ]
    event = {"id": "ev1", "runs": []}
    R._apply_eventexport_registrations(event, regs, entities)
    agi_large = [r for r in event["runs"] if r["laufart"] == "Agility" and r["kategorie"] == "Large"]
    assert len(agi_large) == 2, "Agility muss pro Klasse getrennt bleiben"
    assert {str(r["klasse"]) for r in agi_large} == {"1", "2"}


def test_eventexport_imports_french_extra_fields(fresh_data_dir):
    """FR-Zusatzfelder (FAPAC/Sexe am Hund, N° licence/Club/Régionale am Läufer)
    werden aus dem Portal-Export in dogs.json/handlers.json übernommen."""
    entities, regs = _portal_payload()
    event = {"id": "ev1", "runs": []}
    R._apply_eventexport_registrations(event, regs, entities)

    saved_dogs = {d.get("Lizenznummer"): d for d in utils._load_data("dogs.json")}
    assert saved_dogs["FRA-105002"]["FAPAC"] == "D-12345"
    assert saved_dogs["FRA-105002"]["Sexe"] == "F"
    # CH-Hund ohne FR-Felder bleibt davon unberührt.
    assert not saved_dogs["15333"].get("FAPAC")

    handlers = {h.get("Nachname"): h for h in utils._load_data("handlers.json")}
    assert handlers["Arola"]["FR_Licence"] == "L-98765"
    assert handlers["Arola"]["FR_Club"] == "CC Lyon"
    assert handlers["Arola"]["FR_Regionale"] == "Rhône-Alpes"
