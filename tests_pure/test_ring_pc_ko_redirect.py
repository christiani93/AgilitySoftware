"""
Der Ring-Server (Tkinter-Dashboard) kennt die Event-ID nicht. Der Button
"KO-System öffnen" ruft darum die Hauptserver-Route /ring_pc_ko/<ring> auf,
die das aktive Event auflöst und auf die KO-Cup-Bedienseite dieses Rings
weiterleitet.
"""
import json
import os
import sys

import pytest
from flask import Flask

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
WEB_APP_PATH = os.path.join(PROJECT_ROOT, "web_app")
for _p in (WEB_APP_PATH, PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import blueprints.routes_live as rl  # noqa: E402
import blueprints.routes_ko_cup as kc  # noqa: E402

EVENT_ID = "EVT1"


def _write(data_dir, name, obj):
    with open(os.path.join(data_dir, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = str(tmp_path)
    monkeypatch.setenv("AGILITY_DATA_DIR", data_dir)
    _write(data_dir, "events.json",
           [{"id": EVENT_ID, "Bezeichnung": "Halloween Cup",
             "ko_cup": {"enabled": True, "finals": []}}])
    _write(data_dir, "active_event.json", {"active_event_id": EVENT_ID})
    app = Flask(__name__, template_folder=os.path.join(WEB_APP_PATH, "templates"))
    app.secret_key = "test"
    app.register_blueprint(rl.live_bp)
    app.register_blueprint(kc.ko_cup_bp)
    return app.test_client()


def test_redirects_to_ko_ring_of_active_event(client):
    resp = client.get("/ring_pc_ko/2")
    assert resp.status_code == 302
    loc = resp.headers.get("Location", "")
    assert f"/ko-cup/ring/{EVENT_ID}" in loc
    assert "ring=2" in loc


def test_no_active_event_returns_404(client, tmp_path):
    _write(str(tmp_path), "active_event.json", {})
    resp = client.get("/ring_pc_ko/1")
    assert resp.status_code == 404
