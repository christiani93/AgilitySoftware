"""
Integrationstest fuer die KO-Druckansichten (``ko_final_print``,
``ko_rings_print``).

Treibt die echten HTTP-GET-Routen durch einen Flask-Test-Client gegen einen
temporaeren Datenordner (``AGILITY_DATA_DIR``) und prueft, dass die
Druckseiten rendern und die tragenden Inhalte enthaelten: Endrangliste vor
Duell-Laufzettel, und (ohne Bracket) die Finalisten-Losliste als Fallback.
``ko_rings_print`` prueft die kombinierte, kategorieuebergreifende
Ring-Startliste.

Die Druckvorlagen nutzen den App-Filter ``format_date`` (sonst nur auf der
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


def _make_participant(idx, draw, start, dog=None):
    return {
        "id": f"p{idx}",
        "dog_name": dog or f"Hund{idx}",
        "handler_name": f"Fuehrer{idx}",
        "license_no": f"L{idx}",
        "start_number": start,
        "seeding_rank": idx,
        "draw_number": draw,
        "source": "run",
    }


def _build_large_final():
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


def _build_small_final():
    # 2 Finalisten -> einzige Runde IST bereits die Finalrunde (phase 0),
    # noch ungespielt (Bracket nur gebaut) -> testet die Ring-Startliste
    # auch fuer eine noch nicht begonnene Kategorie.
    parts = [
        _make_participant(1, draw=1, start=1, dog="Mini1"),
        _make_participant(2, draw=2, start=2, dog="Mini2"),
    ]
    return {
        "id": "final_small",
        "group_label": "Small",
        "category_code": "Small",
        "class_level": None,
        "participants": parts,
        "matchups": ko_cup.build_bracket(parts),
        "results": [],
        "is_published": False,
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = str(tmp_path)
    monkeypatch.setenv("AGILITY_DATA_DIR", data_dir)
    event = {
        "id": EVENT_ID,
        "Bezeichnung": "Halloween Cup",
        "Datum": "2026-10-31",
        "ko_cup": {"enabled": True, "finals": [_build_large_final(), _build_small_final()]},
    }
    with open(os.path.join(data_dir, kc.EVENTS_FILE), "w", encoding="utf-8") as f:
        json.dump([event], f, ensure_ascii=False)

    app = Flask(__name__, template_folder=os.path.join(WEB_APP_PATH, "templates"))
    app.secret_key = "test"
    app.jinja_env.filters["format_date"] = lambda d: d  # Stub (nur Haupt-App hat ihn)
    app.jinja_env.globals["_"] = lambda s: s  # Flask-Babel-gettext (nur Haupt-App)
    app.register_blueprint(kc.ko_cup_bp)
    return app.test_client()


def test_print_route_renders_core_sections_endrangliste_first(client):
    resp = client.get(f"/ko-cup/final/{EVENT_ID}/{FINAL_ID}/print")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "KO-Final Large" in html
    assert "Hund1" in html
    # Duell-Laufzettel inkl. Ring-Zuteilung (tragend fuer 2-Ring-Betrieb)
    assert "Duell-Laufzettel" in html
    assert "Ring 1" in html and "Ring 2" in html
    # Startnummern muessen mit (steuern Ringzuteilung)
    assert "10" in html and "40" in html
    # Endrangliste erscheint, sobald Ergebnisse da sind -- UND steht jetzt
    # VOR dem Duell-Laufzettel (Reihenfolge: Endrangliste -> Duell-Laufzettel)
    assert "Endrangliste" in html
    assert html.index("Endrangliste") < html.index("Duell-Laufzettel")
    # Die alte, flache Finalisten-Losliste gibt es nicht mehr, sobald ein
    # Bracket existiert -- ersetzt durch die kombinierte Ring-Startliste.
    assert "Finalisten (" not in html


def test_print_route_404_for_unknown_final(client):
    resp = client.get(f"/ko-cup/final/{EVENT_ID}/does_not_exist/print")
    assert resp.status_code == 404


def test_print_route_shows_finalisten_fallback_before_bracket(tmp_path, monkeypatch):
    data_dir = str(tmp_path)
    monkeypatch.setenv("AGILITY_DATA_DIR", data_dir)
    parts = [_make_participant(1, draw=None, start=None)]
    final = {
        "id": "final_nodraw", "group_label": "Medium", "category_code": "Medium",
        "class_level": None, "participants": parts, "matchups": [],
        "results": [], "is_published": False,
    }
    event = {"id": EVENT_ID, "Bezeichnung": "Halloween Cup", "Datum": "2026-10-31",
             "ko_cup": {"enabled": True, "finals": [final]}}
    with open(os.path.join(data_dir, kc.EVENTS_FILE), "w", encoding="utf-8") as f:
        json.dump([event], f, ensure_ascii=False)
    app = Flask(__name__, template_folder=os.path.join(WEB_APP_PATH, "templates"))
    app.secret_key = "test"
    app.jinja_env.filters["format_date"] = lambda d: d
    app.jinja_env.globals["_"] = lambda s: s
    app.register_blueprint(kc.ko_cup_bp)
    resp = app.test_client().get(f"/ko-cup/final/{EVENT_ID}/final_nodraw/print")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Finalisten (1)" in html
    assert "Hund1" in html


def test_rings_print_route_smoke(client):
    resp = client.get(f"/ko-cup/rings_print/{EVENT_ID}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Startliste Ring 1" in html
    assert "Startliste Ring 2" in html
    assert "Mini1" in html
    assert "Hund1" in html


def test_rings_print_404_for_unknown_event(client):
    resp = client.get("/ko-cup/rings_print/does_not_exist")
    assert resp.status_code == 404


def test_event_ring_startlists_orders_by_phase_then_category():
    """Direkter Test der reinen Sortierlogik (unabhaengig von Namens-
    Wiederholungen ueber Runden hinweg, die eine HTML-String-Suche
    unzuverlaessig machen wuerden): frueheste Runden zuerst; innerhalb
    derselben Phase (0 = Finalrunde) kommt Small vor Large (S-M-I-L)."""
    large = _build_large_final()  # komplett durchgespielt (Runde 1 + 2)
    small = _build_small_final()  # nur Bracket gebaut, ungespielt

    ko = {"finals": [large, small]}
    ring_startlists = kc._event_ring_startlists(ko)
    assert {rs["ring"] for rs in ring_startlists} == {1, 2}

    for rs in ring_startlists:
        categories_in_phase_order = [row["category"] for row in rs["rows"]]
        # Alle Large-Runde-1-Eintraege (phase 1) stehen vor allen Small-
        # Eintraegen (phase 0, einzige Runde) -- fruehe Runden zuerst.
        if "Small" in categories_in_phase_order and "Large" in categories_in_phase_order:
            first_small = categories_in_phase_order.index("Small")
            first_large = categories_in_phase_order.index("Large")
            assert first_large < first_small, (
                "Large-Runde-1 (phase 1) muss vor Small (phase 0) stehen"
            )
