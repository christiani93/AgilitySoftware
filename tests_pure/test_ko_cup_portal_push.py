"""KO-Bracket-Stand wird bei Änderungen ans Portal gespiegelt (read-only Live-Anzeige).

Prüft, dass das Speichern eines Laufs / Matchup-Ergebnisses portal_sync.push_ko_bracket
mit dem vollständigen, display-fertigen Snapshot (alle Finals) auslöst.
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
import portal_sync  # noqa: E402
import blueprints.routes_ko_cup as kc  # noqa: E402

EVENT_ID = "EVT1"
FINAL_ID = "final_large"


def _p(idx, draw, start):
    return {"id": f"p{idx}", "dog_name": f"Hund{idx}", "handler_name": f"F{idx}",
            "license_no": f"L{idx}", "start_number": start, "seeding_rank": idx,
            "draw_number": draw, "source": "run"}


def _event():
    parts = [_p(1, 1, 10), _p(2, 2, 20)]
    final = {"id": FINAL_ID, "group_label": "Large", "category_code": "Large",
             "class_level": None, "participants": parts,
             "matchups": ko_cup.build_bracket(parts), "results": [],
             "is_published": False}
    ko_cup.recompute(final)
    return {"id": EVENT_ID, "Bezeichnung": "Halloween Cup", "external_id": "hcs-ext",
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
    Babel(app)
    app.register_blueprint(kc.ko_cup_bp)

    pushes = []
    monkeypatch.setattr(portal_sync, "push_ko_bracket",
                        lambda settings, event, state: pushes.append((event, state)))
    return app.test_client(), pushes


def test_save_run_triggers_portal_push_with_full_snapshot(ctx):
    client, pushes = ctx
    state = client.get(f"/ko-cup/api/state/{EVENT_ID}").get_json()
    matchup_id = state["finals"][0]["matchups"][0]["id"]

    resp = client.post(
        f"/ko-cup/api/save_run/{EVENT_ID}/{FINAL_ID}/{matchup_id}",
        json={"side": "a", "run": "run1", "time": 41.23, "faults": 0,
              "refusals": 0, "dis": False},
    )
    assert resp.status_code == 200
    assert len(pushes) == 1
    event, pushed = pushes[0]
    assert event["external_id"] == "hcs-ext"
    assert pushed["event_name"] == "Halloween Cup"
    assert len(pushed["finals"]) == 1
    f = pushed["finals"][0]
    assert f["group_label"] == "Large"
    assert f["matchups"][0]["a"]["dog_name"] == "Hund1"
    assert f["matchups"][0]["a_runs"]["run1"]["time"] == 41.23  # Lauf gespiegelt


def test_matchup_result_triggers_portal_push(ctx):
    client, pushes = ctx
    state = client.get(f"/ko-cup/api/state/{EVENT_ID}").get_json()
    matchup_id = state["finals"][0]["matchups"][0]["id"]

    resp = client.post(
        f"/ko-cup/matchup/{EVENT_ID}/{FINAL_ID}/{matchup_id}",
        data={"forfeit": "a"},
    )
    assert resp.status_code in (302, 200)
    assert len(pushes) == 1
    assert pushes[0][1]["finals"][0]["matchups"][0]["forfeit_id"] == "p1"
