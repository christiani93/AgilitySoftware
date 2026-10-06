"""
Integrationstest: die echte HTTP-Route ``team_challenge_config`` (die
"Teamauswahl" im Event-Tag-Betrieb). Treibt den POST-Pfad durch einen
Flask-Test-Client gegen einen temporären Datenordner (``AGILITY_DATA_DIR``)
und prueft die persistierte ``events.json`` zurueck:

  - Team anlegen -> Team in events.json + Mitglieder in den korrekten
    (level x Rolle) Laeufen
  - ungueltiges Team (Lizenz schon vergeben) -> kein zweites Team
  - Team loeschen -> Team + Lauf-Entries weg

Der POST-Zweig der Route endet in einem ``redirect`` -> keine Template-
Render-Abhaengigkeit; die GET-Darstellung bleibt der manuellen Abnahme
vorbehalten.
"""
import json
import os
import sys

import pytest
from flask import Flask

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
WEB_APP_PATH = os.path.join(PROJECT_ROOT, "web_app")
if WEB_APP_PATH not in sys.path:
    sys.path.insert(0, WEB_APP_PATH)

import blueprints.routes_team_challenge as tc  # noqa: E402


EVENT_ID = "EVT1"

# Zwei Large-Hunde Klasse 1/2 -> gueltiges Soft-Team; ein dritter Large als
# Reserve fuer den "Lizenz schon vergeben"-Fall.
DOGS = [
    {"Lizenznummer": "L1", "Hundename": "Rex", "Kategorie": "Large", "Klasse": "2", "Hundefuehrer_ID": "H1"},
    {"Lizenznummer": "L2", "Hundename": "Fido", "Kategorie": "Large", "Klasse": "1", "Hundefuehrer_ID": "H2"},
    {"Lizenznummer": "L3", "Hundename": "Bella", "Kategorie": "Large", "Klasse": "2", "Hundefuehrer_ID": "H3"},
]
HANDLERS = [
    {"id": "H1", "Vorname": "Chris", "Nachname": "Muster"},
    {"id": "H2", "Vorname": "Anna", "Nachname": "Beispiel"},
    {"id": "H3", "Vorname": "Lea", "Nachname": "Test"},
]


def _write_json(data_dir, filename, payload):
    with open(os.path.join(data_dir, filename), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = str(tmp_path)
    monkeypatch.setenv("AGILITY_DATA_DIR", data_dir)
    _write_json(data_dir, tc.DOGS_FILE, DOGS)
    _write_json(data_dir, tc.HANDLERS_FILE, HANDLERS)
    _write_json(data_dir, tc.EVENTS_FILE, [
        {"id": EVENT_ID, "Bezeichnung": "Edelweiss Team-Test",
         "Veranstaltungsart": tc.VERANSTALTUNGSART, "runs": [], "teams": []},
    ])

    app = Flask(__name__)
    app.secret_key = "test"
    app.register_blueprint(tc.team_challenge_bp)
    return app.test_client()


def _load_events(tmp_path):
    with open(os.path.join(str(tmp_path), tc.EVENTS_FILE), encoding="utf-8") as f:
        return json.load(f)


def _event(tmp_path):
    return next(e for e in _load_events(tmp_path) if e["id"] == EVENT_ID)


def _entries_lics(event, team_level, laufart):
    for run in event["runs"]:
        if run.get("is_team_challenge") and run.get("team_level") == team_level and run.get("laufart") == laufart:
            return {(e.get("Lizenznummer") or "").strip() for e in run.get("entries", [])}
    return set()


def test_add_team_persists_team_and_fills_runs(client, tmp_path):
    resp = client.post(f"/team-challenge/config/{EVENT_ID}", data={
        "action": "add_team",
        "kategorie": "Large",
        "level": "soft",
        "mitglied_agility_lizenz": "L1",
        "mitglied_jumping_lizenz": "L2",
        "name": "Die Schnellen",
    })
    assert resp.status_code == 302  # Redirect, kein Template-Render

    event = _event(tmp_path)
    assert len(event["teams"]) == 1
    team = event["teams"][0]
    assert team["kategorie"] == "Large"
    assert team["level"] == "soft"
    assert team["mitglied_agility_lizenz"] == "L1"
    assert team["mitglied_jumping_lizenz"] == "L2"
    assert team["source"] == "software"
    assert team["external_id"]  # stabiler Round-Trip-Schluessel gesetzt

    # Mitglieder landen in den korrekten (level x Rolle) Laeufen ...
    assert _entries_lics(event, "soft", "Agility") == {"L1"}
    assert _entries_lics(event, "soft", "Jumping") == {"L2"}
    # ... und NICHT im jeweils anderen Lauf / anderen Level.
    assert _entries_lics(event, "soft", "Agility") != {"L2"}
    assert _entries_lics(event, "expert", "Agility") == set()


def test_add_team_rejects_reused_license(client, tmp_path):
    base = {"action": "add_team", "kategorie": "Large", "level": "soft"}
    client.post(f"/team-challenge/config/{EVENT_ID}", data={
        **base, "mitglied_agility_lizenz": "L1", "mitglied_jumping_lizenz": "L2", "name": "A",
    })
    # L1 erneut verwenden -> muss abgelehnt werden (Flash-Fehler, kein 2. Team)
    client.post(f"/team-challenge/config/{EVENT_ID}", data={
        **base, "mitglied_agility_lizenz": "L1", "mitglied_jumping_lizenz": "L3", "name": "B",
    })

    event = _event(tmp_path)
    assert len(event["teams"]) == 1
    assert _entries_lics(event, "soft", "Agility") == {"L1"}
    assert "L3" not in _entries_lics(event, "soft", "Jumping")


def test_delete_team_removes_team_and_entries(client, tmp_path):
    client.post(f"/team-challenge/config/{EVENT_ID}", data={
        "action": "add_team", "kategorie": "Large", "level": "soft",
        "mitglied_agility_lizenz": "L1", "mitglied_jumping_lizenz": "L2", "name": "X",
    })
    team_id = _event(tmp_path)["teams"][0]["id"]

    resp = client.post(f"/team-challenge/config/{EVENT_ID}", data={
        "action": "delete_team", "team_id": team_id,
    })
    assert resp.status_code == 302

    event = _event(tmp_path)
    assert event["teams"] == []
    assert _entries_lics(event, "soft", "Agility") == set()
    assert _entries_lics(event, "soft", "Jumping") == set()
