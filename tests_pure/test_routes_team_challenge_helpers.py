"""
Tests für die nicht-Flask-Helfer in blueprints/routes_team_challenge.py
(Lauf-Erzeugung, Team-Validierung, Entry-Sync). `_load_data`/`_save_data`
werden gemonkeypatcht, damit nichts die echten data/*.json-Dateien berührt.
"""
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
WEB_APP_PATH = os.path.join(PROJECT_ROOT, "web_app")
if WEB_APP_PATH not in sys.path:
    sys.path.insert(0, WEB_APP_PATH)

import blueprints.routes_team_challenge as tc  # noqa: E402


DOGS = [
    {"Lizenznummer": "A1", "Hundename": "Rex", "Kategorie": "Large", "Klasse": "2", "Hundefuehrer_ID": "H1"},
    {"Lizenznummer": "A2", "Hundename": "Fido", "Kategorie": "Large", "Klasse": "1", "Hundefuehrer_ID": "H2"},
    {"Lizenznummer": "A3", "Hundename": "Max3", "Kategorie": "Large", "Klasse": "3", "Hundefuehrer_ID": "H1"},
    {"Lizenznummer": "M1", "Hundename": "Nala", "Kategorie": "Medium", "Klasse": "2", "Hundefuehrer_ID": "H3"},
]
HANDLERS = [
    {"id": "H1", "Vorname": "Chris", "Nachname": "Muster"},
    {"id": "H2", "Vorname": "Anna", "Nachname": "Beispiel"},
    {"id": "H3", "Vorname": "Lea", "Nachname": "Test"},
]


def _fake_load_data(filename, default_data=None):
    if filename == tc.DOGS_FILE:
        return list(DOGS)
    if filename == tc.HANDLERS_FILE:
        return list(HANDLERS)
    raise AssertionError(f"unerwarteter _load_data-Aufruf: {filename}")


def test_ensure_team_challenge_runs_erstellt_4_laeufe_und_ist_idempotent():
    event = {"id": "E1", "Veranstaltungsart": "Team-Challenge", "runs": []}
    changed = tc.ensure_team_challenge_runs(event)
    assert changed is True
    assert len(event["runs"]) == 4

    combos = {(r["team_level"], r["laufart"]) for r in event["runs"]}
    assert combos == {("soft", "Agility"), ("soft", "Jumping"),
                       ("expert", "Agility"), ("expert", "Jumping")}

    # Idempotent: zweiter Aufruf legt nichts doppelt an
    changed_again = tc.ensure_team_challenge_runs(event)
    assert changed_again is False
    assert len(event["runs"]) == 4


def test_validate_team_rejects_wrong_category_and_class(monkeypatch):
    monkeypatch.setattr(tc, "_load_data", _fake_load_data)
    event = {"teams": []}

    # A1 (Large, Klasse 2) passt zu Large/soft; M1 (Medium) passt NICHT zur Grösse Large
    err = tc._validate_team(event, "Large", "soft", "A1", "M1")
    assert err is not None and "passt nicht zur Grösse" in err

    # A3 ist Klasse 3 -> passt nicht zu "soft" (1+2)
    err2 = tc._validate_team(event, "Large", "soft", "A1", "A3")
    assert err2 is not None and "passt nicht zu Level" in err2

    # Gültige Kombination
    err3 = tc._validate_team(event, "Large", "soft", "A1", "A2")
    assert err3 is None


def test_validate_team_rejects_license_already_used(monkeypatch):
    monkeypatch.setattr(tc, "_load_data", _fake_load_data)
    event = {"teams": [{
        "id": "T1", "mitglied_agility_lizenz": "A1", "mitglied_jumping_lizenz": "A2",
    }]}
    err = tc._validate_team(event, "Large", "soft", "A1", "A3")
    assert err is not None and "bereits einem anderen Team" in err

    # Beim Editieren des gleichen Teams (exclude_team_id) ist A1 wieder erlaubt
    err2 = tc._validate_team(event, "Large", "soft", "A1", "A2", exclude_team_id="T1")
    assert err2 is None


def test_sync_team_into_runs_fuegt_mitglieder_in_korrekte_laeufe_ein(monkeypatch):
    monkeypatch.setattr(tc, "_load_data", _fake_load_data)
    event = {"Veranstaltungsart": "Team-Challenge", "runs": []}
    tc.ensure_team_challenge_runs(event)

    team = {
        "id": "T1", "level": "soft",
        "mitglied_agility_lizenz": "A1", "mitglied_jumping_lizenz": "A2",
    }
    tc._sync_team_into_runs(event, team, old_team=None)

    runs = tc._team_runs(event)
    agi_entries = {e["Lizenznummer"] for e in runs["soft"]["Agility"]["entries"]}
    jump_entries = {e["Lizenznummer"] for e in runs["soft"]["Jumping"]["entries"]}
    assert agi_entries == {"A1"}
    assert jump_entries == {"A2"}
    # Gegenprobe: Mitglied landet NICHT im falschen Lauf
    assert "A1" not in jump_entries
    assert "A2" not in agi_entries


def test_sync_team_into_runs_entfernt_alten_eintrag_bei_mitglied_tausch(monkeypatch):
    monkeypatch.setattr(tc, "_load_data", _fake_load_data)
    event = {"Veranstaltungsart": "Team-Challenge", "runs": []}
    tc.ensure_team_challenge_runs(event)

    old_team = {"id": "T1", "level": "soft", "mitglied_agility_lizenz": "A1", "mitglied_jumping_lizenz": "A2"}
    tc._sync_team_into_runs(event, old_team, old_team=None)

    # Agility-Mitglied wechselt von A1 auf A2 (A2 war Jumping, jetzt Agility) —
    # realistischer Fall: Rollentausch
    new_team = {"id": "T1", "level": "soft", "mitglied_agility_lizenz": "A2", "mitglied_jumping_lizenz": "A1"}
    tc._sync_team_into_runs(event, new_team, old_team=old_team)

    runs = tc._team_runs(event)
    agi_entries = {e["Lizenznummer"] for e in runs["soft"]["Agility"]["entries"]}
    jump_entries = {e["Lizenznummer"] for e in runs["soft"]["Jumping"]["entries"]}
    assert agi_entries == {"A2"}
    assert jump_entries == {"A1"}


def test_remove_team_from_runs(monkeypatch):
    monkeypatch.setattr(tc, "_load_data", _fake_load_data)
    event = {"Veranstaltungsart": "Team-Challenge", "runs": []}
    tc.ensure_team_challenge_runs(event)
    team = {"id": "T1", "level": "soft", "mitglied_agility_lizenz": "A1", "mitglied_jumping_lizenz": "A2"}
    tc._sync_team_into_runs(event, team, old_team=None)

    tc._remove_team_from_runs(event, team)
    runs = tc._team_runs(event)
    assert runs["soft"]["Agility"]["entries"] == []
    assert runs["soft"]["Jumping"]["entries"] == []
