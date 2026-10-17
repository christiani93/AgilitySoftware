"""Tests fuer den elektronischen Einweiser (Phase 1, read-only).

Prueft das Anzeige-Modell (`build_einweiser_model`) im Normal- UND KO-Modus
sowie den Content-Partial-Endpoint — alles gegen einen temporaeren Datenordner
(`AGILITY_DATA_DIR`), ohne die volle App/Navigation (das Partial erweitert
`layout.html` nicht, daher in einer Minimal-App renderbar).
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

EVENT_ID = "EVT1"


def _normal_event():
    return {
        "id": EVENT_ID,
        "Bezeichnung": "Test-Turnier",
        "num_rings": 2,
        "current_runs_by_ring": {"1": "run_a"},
        "runs": [
            {
                "id": "run_a", "name": "Agility Large 3", "laufart": "Agility",
                "kategorie": "Large", "klasse": "3",
                "current_starter": {"Lizenznummer": "L1"},
                "next_starter": {"Lizenznummer": "L2"},
                "entries": [
                    {"Startnummer": 1, "Lizenznummer": "L1", "Hundefuehrer": "Anna Alpha", "Hundename": "Rex"},
                    {"Startnummer": 2, "Lizenznummer": "L2", "Hundefuehrer": "Bela Beta", "Hundename": "Fay"},
                    {"Startnummer": 3, "Lizenznummer": "L3", "Hundefuehrer": "Cora Gamma", "Hundename": "Yak",
                     "result": {"zeit": 31.2, "fehler": 0, "verweigerungen": 0}},
                ],
            },
            {
                "id": "run_b", "name": "Jumping Large 3", "laufart": "Jumping",
                "kategorie": "Large", "klasse": "3",
                "entries": [
                    {"Startnummer": 1, "Lizenznummer": "L1", "Hundefuehrer": "Anna Alpha", "Hundename": "Rex"},
                    {"Startnummer": 2, "Lizenznummer": "L2", "Hundefuehrer": "Bela Beta", "Hundename": "Fay"},
                ],
            },
        ],
        "schedule": {"rings": {
            "1": {"blocks": [
                {"type": "run", "timing_run_type": "agility", "classes": ["3"], "size_categories": ["large"]},
                {"type": "run", "timing_run_type": "jumping", "classes": ["3"], "size_categories": ["large"]},
            ]},
            "2": {"blocks": []},
        }},
    }


def _ko_event():
    """Minimales, aber echtes KO-Final: 2 Erstrunden-Duelle, eines entschieden."""
    final = {
        "category_code": "L", "group_label": "Large",
        "participants": [
            {"id": "pa", "handler_name": "Anna Alpha", "dog_name": "Rex", "start_number": 1},
            {"id": "pb", "handler_name": "Bela Beta", "dog_name": "Fay", "start_number": 2},
            {"id": "pc", "handler_name": "Cora Gamma", "dog_name": "Yak", "start_number": 3},
            {"id": "pd", "handler_name": "Dirk Delta", "dog_name": "Zoe", "start_number": 4},
        ],
        "matchups": [
            {"round_no": 1, "matchup_type": "winner", "matchup_no": 1,
             "a_id": "pa", "b_id": "pb", "winner_id": "pa"},   # entschieden
            {"round_no": 1, "matchup_type": "winner", "matchup_no": 2,
             "a_id": "pc", "b_id": "pd", "winner_id": None},    # offen
        ],
    }
    return {"id": EVENT_ID, "Bezeichnung": "HCS KO", "num_rings": 2,
            "runs": [], "ko_cup": {"finals": [final]}}


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    for fname in ("dogs.json", "handlers.json", "clubs.json", "judges.json"):
        with open(os.path.join(tmp_path, fname), "w", encoding="utf-8") as f:
            json.dump([], f)
    return tmp_path


def _write_event(data_dir, event):
    with open(os.path.join(data_dir, "events.json"), "w", encoding="utf-8") as f:
        json.dump([event], f, ensure_ascii=False)
    with open(os.path.join(data_dir, "active_event.json"), "w", encoding="utf-8") as f:
        json.dump({"active_event_id": EVENT_ID}, f)


# --- Normalmodus -----------------------------------------------------------

def test_normal_model_whole_day(data_dir):
    _write_event(data_dir, _normal_event())
    import blueprints.routes_einweiser as ew
    model = ew.build_einweiser_model(_normal_event(), 1, hide_finished=False)

    assert model["mode"] == "normal"
    assert model["read_only"] is False  # P2+: normal ist beschreibbar (markieren/umreihen)
    # Ganzer Ring-Tag: beide Laeufe des Rings, nicht nur der aktive
    titles = [(r["laufart"], r["klasse"]) for r in model["runs"]]
    assert ("Agility", "3") in titles and ("Jumping", "3") in titles

    run_a = next(r for r in model["runs"] if r["id"] == "run_a")
    assert run_a["is_active"] is True
    assert run_a["counts"] == {"total": 3, "finished": 1, "pending": 2}
    cur = next(e for e in run_a["entries"] if e["is_current"])
    nxt = next(e for e in run_a["entries"] if e["is_next"])
    assert cur["handler"] == "Anna Alpha" and nxt["handler"] == "Bela Beta"
    assert cur["dog"] == "Rex"

    # Der nicht-aktive Lauf markiert keinen aktuellen Starter
    run_b = next(r for r in model["runs"] if r["id"] == "run_b")
    assert run_b["is_active"] is False
    assert all(not e["is_current"] and not e["is_next"] for e in run_b["entries"])


def test_normal_hide_finished_drops_results(data_dir):
    _write_event(data_dir, _normal_event())
    import blueprints.routes_einweiser as ew
    model = ew.build_einweiser_model(_normal_event(), 1, hide_finished=True)
    run_a = next(r for r in model["runs"] if r["id"] == "run_a")
    # L3 ist beendet -> ausgeblendet, counts zaehlen aber den vollen Lauf
    assert {e["startnummer"] for e in run_a["entries"]} == {1, 2}
    assert run_a["counts"]["total"] == 3 and run_a["counts"]["finished"] == 1


# --- KO-Modus --------------------------------------------------------------

def test_ko_mode_is_readonly_and_hides_decided(data_dir):
    _write_event(data_dir, _ko_event())
    import blueprints.routes_einweiser as ew
    model = ew.build_einweiser_model(_ko_event(), 1, hide_finished=True)
    assert model["mode"] == "ko"
    assert model["read_only"] is True
    # Ring 1 = tiefere Startnummer je Duell: pa (entschieden) + pc (offen).
    # hide_finished -> pa raus, pc bleibt.
    handlers = {r["handler"] for r in model["ko_rows"]}
    assert "Cora Gamma" in handlers
    assert "Anna Alpha" not in handlers
    assert all(not r["decided"] for r in model["ko_rows"])


def test_ko_mode_show_all_includes_decided(data_dir):
    _write_event(data_dir, _ko_event())
    import blueprints.routes_einweiser as ew
    model = ew.build_einweiser_model(_ko_event(), 1, hide_finished=False)
    handlers = {r["handler"] for r in model["ko_rows"]}
    assert {"Anna Alpha", "Cora Gamma"} <= handlers


# --- Content-Endpoint (Partial, keine layout.html-Navigation) --------------

@pytest.fixture
def content_app(data_dir):
    import blueprints.routes_einweiser as ew
    app = Flask(__name__, template_folder=os.path.join(WEB_APP_PATH, "templates"))
    app.secret_key = "test"
    # KO-Labels laufen ueber flask_babel.gettext -> im Request-Kontext muss Babel
    # registriert sein (in der echten App ist es das; hier minimal nachziehen).
    try:
        from flask_babel import Babel
        Babel(app)
    except Exception:
        pass
    app.register_blueprint(ew.einweiser_bp)
    return app


def test_content_endpoint_normal_200(content_app, data_dir):
    _write_event(data_dir, _normal_event())
    resp = content_app.test_client().get("/api/render_einweiser_content/1")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:1500]
    html = resp.get_data(as_text=True)
    assert "Anna Alpha" in html and "Bela Beta" in html


def test_content_endpoint_ko_200(content_app, data_dir):
    _write_event(data_dir, _ko_event())
    resp = content_app.test_client().get("/api/render_einweiser_content/1?hide_finished=1")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:1500]
    html = resp.get_data(as_text=True)
    assert "KO-Modus" in html
    assert "Cora Gamma" in html and "Anna Alpha" not in html


# --- P2/P3: nicht-autoritatives Markieren ----------------------------------

def _read_entry(data_dir, run_id, lic):
    with open(os.path.join(data_dir, "events.json"), "r", encoding="utf-8") as f:
        ev = json.load(f)[0]
    run = next(r for r in ev["runs"] if r["id"] == run_id)
    return next(e for e in run["entries"] if e["Lizenznummer"] == lic)


def test_mark_set_and_toggle_clear(content_app, data_dir):
    _write_event(data_dir, _normal_event())
    c = content_app.test_client()

    r = c.post("/einweiser/api/mark/EVT1/run_a", json={"license_number": "L1", "mark": "ready"})
    assert r.status_code == 200 and r.get_json()["mark"] == "ready"
    assert _read_entry(data_dir, "run_a", "L1").get("einweiser_mark") == "ready"

    # 'none' loescht die Markierung
    r = c.post("/einweiser/api/mark/EVT1/run_a", json={"license_number": "L1", "mark": "none"})
    assert r.status_code == 200 and r.get_json()["mark"] == ""
    assert "einweiser_mark" not in _read_entry(data_dir, "run_a", "L1")


def test_mark_does_not_write_result(content_app, data_dir):
    """Markieren ist nicht-autoritativ: kein Resultat, kein current_starter-Shift."""
    _write_event(data_dir, _normal_event())
    c = content_app.test_client()
    c.post("/einweiser/api/mark/EVT1/run_a", json={"license_number": "L2", "mark": "absent"})
    entry = _read_entry(data_dir, "run_a", "L2")
    assert "result" not in entry  # KEINE DNS-Wertung
    with open(os.path.join(data_dir, "events.json"), "r", encoding="utf-8") as f:
        run = json.load(f)[0]["runs"][0]
    assert run["current_starter"].get("Lizenznummer") == "L1"  # unveraendert


def test_mark_invalid_rejected(content_app, data_dir):
    _write_event(data_dir, _normal_event())
    r = content_app.test_client().post(
        "/einweiser/api/mark/EVT1/run_a", json={"license_number": "L1", "mark": "bogus"})
    assert r.status_code == 400


def test_mark_blocked_in_ko(content_app, data_dir):
    _write_event(data_dir, _ko_event())
    r = content_app.test_client().post(
        "/einweiser/api/mark/EVT1/any", json={"license_number": "pa", "mark": "ready"})
    assert r.status_code == 403


# --- P4: Umreihen (start_order) --------------------------------------------

def test_sort_backward_compatible_without_start_order():
    """Ohne start_order: Startnummer aufsteigend, läufig ans Ende (wie bisher)."""
    from utils import sort_entries_for_startlist
    a = {"Lizenznummer": "A", "Startnummer": 1}
    b = {"Lizenznummer": "B", "Startnummer": 2, "is_in_season": True}  # läufig
    c = {"Lizenznummer": "C", "Startnummer": 3}
    order = [e["Lizenznummer"] for e in sort_entries_for_startlist([c, b, a])]
    assert order == ["A", "C", "B"]


def test_sort_manual_order_wins():
    from utils import sort_entries_for_startlist
    a = {"Lizenznummer": "A", "Startnummer": 1, "start_order": 2}
    b = {"Lizenznummer": "B", "Startnummer": 2, "start_order": 0, "is_in_season": True}
    c = {"Lizenznummer": "C", "Startnummer": 3, "start_order": 1}
    order = [e["Lizenznummer"] for e in sort_entries_for_startlist([a, b, c])]
    assert order == ["B", "C", "A"]  # manuelle Reihenfolge schlaegt Startnr + läufig


def test_reorder_moves_and_assigns_all(content_app, data_dir):
    _write_event(data_dir, _normal_event())
    c = content_app.test_client()
    r = c.post("/einweiser/api/reorder/EVT1/run_a", json={"license_number": "L1", "direction": "down"})
    assert r.status_code == 200 and r.get_json().get("success") is True

    from utils import sort_entries_for_startlist
    with open(os.path.join(data_dir, "events.json"), "r", encoding="utf-8") as f:
        run = json.load(f)[0]["runs"][0]
    # Alle Eintraege haben jetzt eine explizite start_order
    assert all("start_order" in e for e in run["entries"])
    order = [e["Lizenznummer"] for e in sort_entries_for_startlist(run["entries"])]
    assert order == ["L2", "L1", "L3"]


def test_reorder_top_up_is_noop(content_app, data_dir):
    _write_event(data_dir, _normal_event())
    r = content_app.test_client().post(
        "/einweiser/api/reorder/EVT1/run_a", json={"license_number": "L1", "direction": "up"})
    assert r.status_code == 200 and r.get_json().get("noop") is True


def test_reorder_blocked_in_ko(content_app, data_dir):
    _write_event(data_dir, _ko_event())
    r = content_app.test_client().post(
        "/einweiser/api/reorder/EVT1/any", json={"license_number": "pa", "direction": "down"})
    assert r.status_code == 403


# --- P5: Robustheit --------------------------------------------------------

def test_mark_unknown_event_and_run_404(content_app, data_dir):
    _write_event(data_dir, _normal_event())
    c = content_app.test_client()
    assert c.post("/einweiser/api/mark/NOPE/run_a",
                  json={"license_number": "L1", "mark": "ready"}).status_code == 404
    assert c.post("/einweiser/api/mark/EVT1/nope",
                  json={"license_number": "L1", "mark": "ready"}).status_code == 404


def test_reorder_unknown_run_404_and_bad_direction_400(content_app, data_dir):
    _write_event(data_dir, _normal_event())
    c = content_app.test_client()
    assert c.post("/einweiser/api/reorder/EVT1/nope",
                  json={"license_number": "L1", "direction": "down"}).status_code == 404
    assert c.post("/einweiser/api/reorder/EVT1/run_a",
                  json={"license_number": "L1", "direction": "sideways"}).status_code == 400
