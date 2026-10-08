"""
Integrationstest fuer die "normalen" Startlisten-Druckrouten
(``print_startlists``, ``print_startlists_by_schedule``).

Deckt den Fix vom 2026-10-07 ab: beide Routen gaben bisher KEIN Eventlogo
an ``print/_print_header.html`` weiter (im Unterschied zu den KO-Drucksachen,
die bereits ``get_event_logo_data_uris()`` nutzen) -- der gemeinsame Header
fiel deshalb immer auf die Platzhalter-Box zurueck.

Treibt die echten HTTP-GET-Routen durch einen Flask-Test-Client gegen einen
temporaeren Datenordner (``AGILITY_DATA_DIR``).
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

import blueprints.routes_print as rp  # noqa: E402

EVENT_ID = "EVT1"


def _event():
    return {
        "id": EVENT_ID,
        "Bezeichnung": "Test-Turnier",
        "Datum": "2026-10-10",
        "runs": [
            {
                "id": "run1",
                "name": "Agility Kl.3",
                "laufart": "Agility",
                "kategorie": "Large",
                "klasse": "3",
                "entries": [
                    {"Startnummer": 1, "Hundefuehrer": "Fuehrer1", "Hundename": "Hund1",
                     "Lizenznummer": "L1", "Rasse": "", "Verein": ""},
                    {"Startnummer": 2, "Hundefuehrer": "Fuehrer2", "Hundename": "Hund2",
                     "Lizenznummer": "L2", "Rasse": "", "Verein": ""},
                ],
            },
        ],
        # Kein "schedule" -> print_startlists faellt auf event.runs zurueck,
        # print_startlists_by_schedule zeigt den "Kein Zeitplan"-Fallback.
    }


@pytest.fixture
def app_and_dir(tmp_path, monkeypatch):
    data_dir = str(tmp_path)
    monkeypatch.setenv("AGILITY_DATA_DIR", data_dir)
    for fname in ("dogs.json", "handlers.json", "clubs.json"):
        with open(os.path.join(data_dir, fname), "w", encoding="utf-8") as f:
            json.dump([], f)
    with open(os.path.join(data_dir, "events.json"), "w", encoding="utf-8") as f:
        json.dump([_event()], f, ensure_ascii=False)

    app = Flask(__name__, template_folder=os.path.join(WEB_APP_PATH, "templates"))
    app.secret_key = "test"
    app.jinja_env.filters["format_date"] = lambda d: d
    app.jinja_env.globals["_"] = lambda s: s
    app.register_blueprint(rp.print_bp)
    return app, data_dir


def test_print_startlists_renders_with_placeholder_logo(app_and_dir):
    app, _ = app_and_dir
    resp = app.test_client().get(f"/print/startlists/{EVENT_ID}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Hund1" in html and "Hund2" in html
    # Kein Logo hinterlegt -> Platzhalter-Box statt <img>, aber kein Crash.
    assert "print-header__logo-box" in html
    assert "<img" not in html


def test_print_startlists_embeds_event_logo_as_data_uri(app_and_dir):
    app, data_dir = app_and_dir
    logos_dir = os.path.join(data_dir, "logos", EVENT_ID)
    os.makedirs(logos_dir, exist_ok=True)
    with open(os.path.join(logos_dir, "event.png"), "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"0" * 20)  # Dummy-Inhalt reicht fuer base64-Embed

    with open(os.path.join(data_dir, "events.json"), "r+", encoding="utf-8") as f:
        events = json.load(f)
        events[0]["event_logo_filename"] = "event.png"
        f.seek(0)
        json.dump(events, f, ensure_ascii=False)
        f.truncate()

    resp = app.test_client().get(f"/print/startlists/{EVENT_ID}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'src="data:image/png;base64,' in html


def test_print_startlists_by_schedule_smoke_without_schedule(app_and_dir):
    app, _ = app_and_dir
    resp = app.test_client().get(f"/print/startlists_by_schedule/{EVENT_ID}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Kein Zeitplan vorhanden" in html
    assert "print-header__logo-box" in html


def test_print_startlists_404_for_unknown_event(app_and_dir):
    app, _ = app_and_dir
    resp = app.test_client().get("/print/startlists/does_not_exist")
    assert resp.status_code == 404
