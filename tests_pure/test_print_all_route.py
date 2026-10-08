"""Integrationstest für den Sammeldruck (``print_all``, /print/all/<event_id>).

Treibt die echte HTTP-GET-Route durch einen Flask-Test-Client gegen einen
temporären Datenordner (``AGILITY_DATA_DIR``) und prüft, dass die drei Bündel
(Teilnehmerinfo / Einweiser / Ringbüro) in einem Dokument gerendert werden.
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
        "num_rings": 2,
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
        "schedule": {
            "rings": {
                "1": {"blocks": [
                    {
                        "type": "run",
                        "timing_run_type": "agility",
                        "classes": ["3"],
                        "size_categories": ["large"],
                        "judge_id": "J1",
                        "sort": {"primary": {"field": "startnummer", "direction": "asc"}},
                    }
                ]},
                "2": {"blocks": []},
            }
        },
    }


@pytest.fixture
def app_and_dir(tmp_path, monkeypatch):
    data_dir = str(tmp_path)
    monkeypatch.setenv("AGILITY_DATA_DIR", data_dir)
    for fname in ("dogs.json", "handlers.json", "clubs.json"):
        with open(os.path.join(data_dir, fname), "w", encoding="utf-8") as f:
            json.dump([], f)
    with open(os.path.join(data_dir, "judges.json"), "w", encoding="utf-8") as f:
        json.dump([{"id": "J1", "firstname": "Max", "lastname": "Muster"}], f, ensure_ascii=False)
    with open(os.path.join(data_dir, "events.json"), "w", encoding="utf-8") as f:
        json.dump([_event()], f, ensure_ascii=False)

    app = Flask(__name__, template_folder=os.path.join(WEB_APP_PATH, "templates"))
    app.secret_key = "test"
    app.jinja_env.filters["format_date"] = lambda d: d
    app.jinja_env.globals["_"] = lambda s: s
    app.register_blueprint(rp.print_bp)
    return app, data_dir


def test_print_all_renders_three_bundles(app_and_dir):
    app, _ = app_and_dir
    resp = app.test_client().get(f"/print/all/{EVENT_ID}")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:2000]
    html = resp.get_data(as_text=True)
    # Drei Bündel-Titelseiten
    assert "Teilnehmerinfo" in html
    assert "Einweiser" in html
    assert "Ringbüro" in html
    # Startlisten-Inhalt (Bündel 1)
    assert "Hund1" in html and "Hund2" in html
    # Pro-Ring-Titel (Bündel 2 & 3)
    assert "Ring 1" in html and "Ring 2" in html
    # Richter aus judges.json (Einweiser/Ringbüro-Zeitplan + Scribe-Meta)
    assert "Max Muster" in html


def test_print_all_404_for_unknown_event(app_and_dir):
    app, _ = app_and_dir
    resp = app.test_client().get("/print/all/does_not_exist")
    assert resp.status_code == 404
