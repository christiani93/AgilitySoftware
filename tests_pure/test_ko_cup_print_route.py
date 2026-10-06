"""
Integrationstest fuer die KO-Druckansicht (``ko_final_print``).

Treibt die echte HTTP-GET-Route durch einen Flask-Test-Client gegen einen
temporaeren Datenordner (``AGILITY_DATA_DIR``) und prueft, dass die
Druckseite rendert und die tragenden Inhalte enthaelt: Finalisten,
Duell-Laufzettel mit Ring-Zuteilung und die Endrangliste.

Die Druckvorlage nutzt den App-Filter ``format_date`` (sonst nur auf der
Haupt-App registriert) — im Test als Identitaet gestubbt.
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

import ko_cup  # noqa: E402
import blueprints.routes_ko_cup as kc  # noqa: E402

EVENT_ID = "EVT1"
FINAL_ID = "final_large"


def _make_participant(idx, draw, start):
    return {
        "id": f"p{idx}",
        "dog_name": f"Hund{idx}",
        "handler_name": f"Fuehrer{idx}",
        "license_no": f"L{idx}",
        "start_number": start,
        "seeding_rank": idx,
        "draw_number": draw,
        "source": "run",
    }


def _build_final():
    # 4 Finalisten -> Halbfinals, Final, Spiel um Platz 3
    parts = [
        _make_participant(1, draw=1, start=10),
        _make_participant(2, draw=2, start=20),
        _make_participant(3, draw=3, start=30),
        _make_participant(4, draw=4, start=40),
    ]
    final = {
        "id": FINAL_ID,
        "group_label": "Large",
        "category_code": "Large",
        "class_level": None,
        "participants": parts,
        "matchups": ko_cup.build_bracket(parts),
        "results": [],
        "is_published": False,
    }
    # Komplettes Turnier durchspielen, damit Zeiten/Totals UND die
    # Endrangliste in der Druckansicht erscheinen.
    def _fast(m):  # Seite A gewinnt klar
        m["a"] = {"run1": {"time": 20.0, "faults": 0, "refusals": 0, "dis": False},
                  "run2": {"time": 21.0, "faults": 1, "refusals": 0, "dis": False}}
        m["b"] = {"run1": {"time": 25.0, "faults": 0, "refusals": 0, "dis": False},
                  "run2": {"time": 24.0, "faults": 0, "refusals": 0, "dis": False}}

    for m in [m for m in final["matchups"] if m["round_no"] == 1]:
        _fast(m)
    ko_cup.recompute(final)  # loest Halbfinals -> Final + Spiel um Platz 3 bekommen Teams
    for m in final["matchups"]:
        if m["round_no"] == 2:  # Final + Spiel um Platz 3
            _fast(m)
    ko_cup.recompute(final)
    return final


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = str(tmp_path)
    monkeypatch.setenv("AGILITY_DATA_DIR", data_dir)
    event = {
        "id": EVENT_ID,
        "Bezeichnung": "Halloween Cup",
        "Datum": "2026-10-31",
        "ko_cup": {"enabled": True, "finals": [_build_final()]},
    }
    with open(os.path.join(data_dir, kc.EVENTS_FILE), "w", encoding="utf-8") as f:
        json.dump([event], f, ensure_ascii=False)

    app = Flask(__name__, template_folder=os.path.join(WEB_APP_PATH, "templates"))
    app.secret_key = "test"
    app.jinja_env.filters["format_date"] = lambda d: d  # Stub (nur Haupt-App hat ihn)
    app.register_blueprint(kc.ko_cup_bp)
    return app.test_client()


def test_print_route_renders_core_sections(client):
    resp = client.get(f"/ko-cup/final/{EVENT_ID}/{FINAL_ID}/print")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    # Kopf + Finalisten
    assert "KO-Final Large" in html
    assert "Finalisten" in html
    assert "Hund1" in html
    # Duell-Laufzettel inkl. Ring-Zuteilung (tragend fuer 2-Ring-Betrieb)
    assert "Duell-Laufzettel" in html
    assert "Ring 1" in html and "Ring 2" in html
    # Startnummern muessen mit (steuern Ringzuteilung)
    assert "10" in html and "40" in html
    # Endrangliste erscheint, sobald Ergebnisse da sind
    assert "Endrangliste" in html


def test_print_route_404_for_unknown_final(client):
    resp = client.get(f"/ko-cup/final/{EVENT_ID}/does_not_exist/print")
    assert resp.status_code == 404
