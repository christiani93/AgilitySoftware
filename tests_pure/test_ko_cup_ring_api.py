"""
Integrationstest fuer die KO-Live-Endpunkte (2-Ring-Betrieb):

  - GET  /ko-cup/api/state/<event_id>            -> JSON-Stand fuer den Ring-PC
  - POST /ko-cup/api/save_run/<...>/<matchup>    -> einen Lauf (Team/Lauf)
                                                    vom Ring-PC schreiben

Treibt die echten HTTP-Routen durch einen Flask-Test-Client gegen einen
temporaeren Datenordner (``AGILITY_DATA_DIR``) und prueft die persistierte
``events.json`` + die JSON-Antworten zurueck.
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


def _p(idx, draw, start):
    return {"id": f"p{idx}", "dog_name": f"Hund{idx}", "handler_name": f"F{idx}",
            "license_no": f"L{idx}", "start_number": start, "seeding_rank": idx,
            "draw_number": draw, "source": "run"}


def _event():
    parts = [_p(1, 1, 10), _p(2, 2, 20)]  # 2 Finalisten -> genau 1 Duell (Final)
    final = {"id": FINAL_ID, "group_label": "Large", "category_code": "Large",
             "class_level": None, "participants": parts,
             "matchups": ko_cup.build_bracket(parts), "results": [],
             "is_published": False}
    ko_cup.recompute(final)
    return {"id": EVENT_ID, "Bezeichnung": "Halloween Cup",
            "ko_cup": {"enabled": True, "finals": [final]}}


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    data_dir = str(tmp_path)
    monkeypatch.setenv("AGILITY_DATA_DIR", data_dir)
    with open(os.path.join(data_dir, kc.EVENTS_FILE), "w", encoding="utf-8") as f:
        json.dump([_event()], f, ensure_ascii=False)
    app = Flask(__name__, template_folder=os.path.join(WEB_APP_PATH, "templates"))
    app.secret_key = "test"
    from flask_babel import Babel
    Babel(app)  # gettext() in ko_cup.round_label braucht die babel-Extension
    app.register_blueprint(kc.ko_cup_bp)
    return app.test_client(), tmp_path


def _load_final(tmp_path):
    with open(os.path.join(str(tmp_path), kc.EVENTS_FILE), encoding="utf-8") as f:
        ev = json.load(f)[0]
    return ev["ko_cup"]["finals"][0]


def test_ring_page_links_to_its_own_ring_startlist(ctx):
    """Der Ring-PC braucht einen direkten Link zur Ring-Startliste (statt
    ueber die Admin-Config zu gehen) -- Anker springt zum richtigen Ring."""
    client, _ = ctx
    resp = client.get(f"/ko-cup/ring/{EVENT_ID}?ring=2")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert f"/ko-cup/rings_print/{EVENT_ID}#ring-2" in html


def test_state_returns_matchup_with_ring_assignment(ctx):
    client, _ = ctx
    resp = client.get(f"/ko-cup/api/state/{EVENT_ID}")
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["success"] and len(j["finals"]) == 1
    f = j["finals"][0]
    assert f["group_label"] == "Large"
    m = f["matchups"][0]
    # tiefere Startnummer (10) -> Ring 1 fuer Lauf 1
    assert m["rings"]["a"]["run1"] == 1
    assert m["rings"]["b"]["run1"] == 2
    assert m["a"]["start_number"] == 10 and m["b"]["start_number"] == 20


def test_save_run_writes_slot_and_decides_winner(ctx):
    client, tmp_path = ctx
    m_id = _load_final(tmp_path)["matchups"][0]["id"]

    # Beide Teams, beide Laeufe erfassen (A schneller)
    runs = [
        ("a", "run1", 20.0), ("a", "run2", 20.0),
        ("b", "run1", 25.0), ("b", "run2", 25.0),
    ]
    for side, run, t in runs:
        r = client.post(f"/ko-cup/api/save_run/{EVENT_ID}/{FINAL_ID}/{m_id}",
                        json={"side": side, "run": run, "time": t,
                              "faults": 0, "refusals": 0, "dis": False})
        assert r.status_code == 200 and r.get_json()["success"]

    final = _load_final(tmp_path)
    m = final["matchups"][0]
    assert m["a"]["run1"]["time"] == 20.0
    assert m["winner_id"] == "p1"  # A (40s) < B (50s)
    # Endrangliste gesetzt
    ranks = {r["participant_id"]: r["rank"] for r in final["results"]}
    assert ranks["p1"] == 1 and ranks["p2"] == 2


def test_save_run_penalties_change_winner(ctx):
    client, tmp_path = ctx
    m_id = _load_final(tmp_path)["matchups"][0]["id"]
    # A roh schneller, aber 2 Fehler (+4s) pro Lauf -> B gewinnt
    client.post(f"/ko-cup/api/save_run/{EVENT_ID}/{FINAL_ID}/{m_id}",
                json={"side": "a", "run": "run1", "time": 20.0, "faults": 2})
    client.post(f"/ko-cup/api/save_run/{EVENT_ID}/{FINAL_ID}/{m_id}",
                json={"side": "a", "run": "run2", "time": 20.0, "faults": 2})
    client.post(f"/ko-cup/api/save_run/{EVENT_ID}/{FINAL_ID}/{m_id}",
                json={"side": "b", "run": "run1", "time": 23.0})
    r = client.post(f"/ko-cup/api/save_run/{EVENT_ID}/{FINAL_ID}/{m_id}",
                    json={"side": "b", "run": "run2", "time": 23.0})
    assert r.get_json()["matchup"]["winner_id"] == "p2"


def test_save_run_rejects_bad_side(ctx):
    client, tmp_path = ctx
    m_id = _load_final(tmp_path)["matchups"][0]["id"]
    r = client.post(f"/ko-cup/api/save_run/{EVENT_ID}/{FINAL_ID}/{m_id}",
                    json={"side": "x", "run": "run1", "time": 10.0})
    assert r.status_code == 400


def test_display_page_renders(ctx):
    """Zuschauer-/Kiosk-Anzeige rendert und zieht ihren Stand aus der
    bestehenden JSON-State-Route (read-only, selbst-aktualisierend)."""
    client, _ = ctx
    r = client.get(f"/ko-cup/display/{EVENT_ID}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "KO" in html and "Halloween Cup" in html
    # Lädt den Stand aus der vorhandenen State-API und reagiert auf ko_update.
    assert "/ko-cup/api/state/" in html
    assert "ko_update" in html


def test_display_page_category_filter(ctx):
    """?cat=L wird als Grössenklassen-Filter in die Seite durchgereicht."""
    client, _ = ctx
    r = client.get(f"/ko-cup/display/{EVENT_ID}?cat=L")
    assert r.status_code == 200
    assert 'ONLY_CAT   = "L"' in r.get_data(as_text=True)


def test_ko_display_control_forwards_to_event_room(monkeypatch):
    """Der Handler reicht ein Fernsteuerungs-Kommando vom Ring-PC 1:1 an alle
    Displays im selben Event-Room weiter (Raum `event:<id>`, dasselbe Muster
    wie announcer_update/ring_monitor)."""
    emitted = []
    monkeypatch.setattr(kc.socketio, "emit", lambda event, *a, **kw: emitted.append((event, a, kw)))

    kc._on_ko_display_control({"event_id": EVENT_ID, "action": "show_category", "category_code": "Large"})

    assert len(emitted) == 1
    event, args, kwargs = emitted[0]
    assert event == "ko_display_control"
    assert args[0]["category_code"] == "Large"
    assert kwargs["room"] == f"event:{EVENT_ID}"


def test_ko_display_control_ignores_missing_event_id(monkeypatch):
    emitted = []
    monkeypatch.setattr(kc.socketio, "emit", lambda event, *a, **kw: emitted.append((event, a, kw)))
    kc._on_ko_display_control({"action": "rotate", "enabled": True})
    assert emitted == []


def test_ring_page_renders(ctx):
    client, _ = ctx
    r = client.get(f"/ko-cup/ring/{EVENT_ID}?ring=2")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "KO-Ring 2" in html
    # Ring-Server-Port folgt der Konvention 5000 + Ring-Nr (hier Ring 2 -> 5002).
    assert "RING_NO  = 2" in html
    assert "(5000 + RING_NO)" in html
    # Zählung läuft über den Ring-Server (Bereit-Button + F/V-Zähler).
    assert 'id="readyBtn"' in html
    assert "increment_counter" in html
    # DIS: wird GEZÄHLT (+/- Buttons, Taste D), 5 Sek pro DIS, mehrere pro Lauf --
    # statt Lauf-Abbruch wie am normalen Ring-PC-Dashboard; unterbricht den
    # TIMY-Lauf nicht.
    assert 'id="disPlus"' in html
    assert 'id="disMinus"' in html
    assert "count_dis" in html
    assert 'k === "d"' in html
    # Fernsteuerung des Zuschauer-Monitors (ko_cup_display.html) über denselben
    # Haupt-Server-Socket -- Kategorie-Buttons + Rotations-Toggle.
    assert 'id="monitorTabs"' in html
    assert 'id="monitorRotateBtn"' in html
    assert "ko_display_control" in html


def test_display_page_joins_room_and_listens_for_remote_control(ctx):
    """Die Kiosk-Anzeige tritt dem Event-Room bei (wie Ring-Monitor/Sprecher)
    und reagiert auf Fernsteuerungs-Kommandos vom Ring-PC."""
    client, _ = ctx
    r = client.get(f"/ko-cup/display/{EVENT_ID}")
    html = r.get_data(as_text=True)
    assert "join_room" in html
    assert f"event:${{EVENT_ID}}" in html.replace(" ", "")  # Template-Literal `event:${EVENT_ID}`
    assert "ko_display_control" in html
    assert "show_category" in html
