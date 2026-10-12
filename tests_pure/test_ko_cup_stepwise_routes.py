"""
Integrationstest fuer den SCHRITTWEISEN KO-Ablauf ueber die echten HTTP-Routen:

- Config-POST ``derive_run``: leitet NUR einen Schluessel-Lauf ab und haengt die
  Finalisten an (eventuebergreifend via ``source_event_id`` aus einem separaten
  Freitag-Event). Ein zweiter Lauf haengt an, ohne den ersten zu ersetzen.
- Final-POST ``draw_remaining``: lost NUR die noch unglosten Finalisten, die
  bereits vergebenen Losnummern bleiben erhalten.

Treibt einen Flask-Test-Client gegen einen temporaeren Datenordner
(``AGILITY_DATA_DIR``). Zwei Events liegen vor: ein Freitag-Tunnellauf-Event und
das Samstag-Final-Event, dessen Tunnellauf-Schluessel per ``source_event_id`` auf
den Freitag zeigt.
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

import blueprints.routes_ko_cup as kc  # noqa: E402

FR_ID = "FR_EVT"
SA_ID = "SA_EVT"


def _entry(lic, dog, kat, cls, zeit):
    return {
        "Lizenznummer": lic, "Hundename": dog, "Hundefuehrer": f"HF {dog}",
        "Kategorie": kat, "Klasse": str(cls),
        "result": {"zeit": zeit, "fehler": 0, "verweigerungen": 0, "disqualifikation": None},
    }


def _run(rid, laufart, kat, cls, entries):
    return {
        "id": rid, "name": f"{laufart} {kat} {cls}", "laufart": laufart,
        "kategorie": kat, "klasse": str(cls), "entries": entries,
        "laufdaten": {"standardzeit_sct": "999"},
    }


def _friday():
    return {
        "id": FR_ID, "Bezeichnung": "HCS Freitag", "Datum": "2026-10-30",
        "runs": [_run("t_l", "Tunnellauf", "Large", 1, [
            _entry("A", "Alpha", "Large", 1, 20.0),
            _entry("B", "Bravo", "Large", 1, 21.0),
            _entry("C", "Charlie", "Large", 1, 22.0),
        ])],
    }


def _saturday():
    return {
        "id": SA_ID, "Bezeichnung": "HCS Samstag", "Datum": "2026-10-31",
        "runs": [_run("a_l", "Agility", "Large", 1, [
            _entry("A", "Alpha", "Large", 1, 19.0),   # schon via Tunnel -> rueckt nach
            _entry("D", "Delta", "Large", 1, 25.0),   # neuer Agility-Quali
        ])],
        "ko_cup": {
            "enabled": True,
            "qualification": {"runs": [
                {"label": "Tunnellauf", "match": {"laufart": "Tunnellauf"},
                 "split_by_class": False, "source_event_id": FR_ID,
                 "spots": {"Large": 2, "Intermediate": 0, "Medium": 0, "Small": 0}},
                {"label": "Agility", "match": {"laufart": "Agility"},
                 "split_by_class": True,
                 "spots": {"Large": 1, "Intermediate": 0, "Medium": 0, "Small": 0}},
            ]},
            "finals": [],
        },
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = str(tmp_path)
    monkeypatch.setenv("AGILITY_DATA_DIR", data_dir)
    with open(os.path.join(data_dir, kc.EVENTS_FILE), "w", encoding="utf-8") as f:
        json.dump([_friday(), _saturday()], f, ensure_ascii=False)

    app = Flask(__name__, template_folder=os.path.join(WEB_APP_PATH, "templates"))
    app.secret_key = "test"
    from flask_babel import Babel
    Babel(app)
    app.jinja_env.filters["format_date"] = lambda d: d
    app.jinja_env.globals["_"] = lambda s: s
    # layout.html erwartet Context-Globals des Haupt-App-Context-Processors.
    app.jinja_env.globals.update(python_version="3.13", flask_version="3")
    # layout.html referenziert Haupt-App-Endpoints (home, events, ...), die hier
    # nicht registriert sind -> Build-Fehler auf "#" abfangen, damit das echte
    # Config-Template rendert.
    app.handle_url_build_error = lambda error, endpoint, values: "#"
    app.register_blueprint(kc.ko_cup_bp)
    return app.test_client()


def _load(client_data_dir):
    with open(os.path.join(client_data_dir, kc.EVENTS_FILE), encoding="utf-8") as f:
        events = json.load(f)
    return {e["id"]: e for e in events}


def _large(sa):
    return next(f for f in sa["ko_cup"]["finals"] if f["category_code"] == "Large")


def test_config_renders_per_run_derive_buttons(client):
    resp = client.get(f"/ko-cup/config/{SA_ID}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Schrittweise" in html
    # Tunnellauf (kombiniert) als ganzer Lauf, Agility (split) pro Klasse.
    assert "Tunnellauf ableiten" in html
    assert "Agility ableiten" not in html
    assert 'name="class"' in html
    assert "Kl.&nbsp;1 ableiten" in html
    assert "Kl.&nbsp;3 ableiten" in html


def test_derive_run_per_class_only_that_class(client, tmp_path):
    data_dir = str(tmp_path)
    # Agility (Lauf 1, split) NUR Klasse 1 ableiten -> Delta rueckt nach,
    # and keine anderen Klassen (Sa-Event hat nur Kl1).
    r = client.post(f"/ko-cup/config/{SA_ID}",
                    data={"action": "derive_run", "run_index": "1", "class": "1"})
    assert r.status_code == 302
    sa = _load(data_dir)[SA_ID]
    large = _large(sa)
    parts = [p for p in large["participants"] if p.get("quali_label") == "Agility"]
    # Ohne vorherige Tunnel-Ableitung ist Alpha (Kl1-Schnellster) der Quali.
    assert {p["dog_name"] for p in parts} == {"Alpha"}
    assert all(p["from_class"] == 1 for p in parts)


def test_save_draws_all_cross_category(client, tmp_path):
    data_dir = str(tmp_path)
    # Tunnellauf ableiten -> Alpha, Bravo im Large-Final (noch unglost).
    client.post(f"/ko-cup/config/{SA_ID}",
                data={"action": "derive_run", "run_index": "0"})
    sa = _load(data_dir)[SA_ID]
    large = _large(sa)
    ids = {p["dog_name"]: p["id"] for p in large["participants"]}

    # Config-Seite zeigt die kategorieübergreifende Losnummern-Liste.
    html = client.get(f"/ko-cup/config/{SA_ID}").get_data(as_text=True)
    assert "Losnummern eintragen" in html
    assert f'name="draw_{ids["Alpha"]}"' in html

    # Losnummern direkt über das Formular speichern (Feld je Finalist = draw_<id>).
    r = client.post(f"/ko-cup/config/{SA_ID}", data={
        "action": "save_draws_all",
        f"draw_{ids['Alpha']}": "2",
        f"draw_{ids['Bravo']}": "1",
    })
    assert r.status_code == 302
    sa = _load(data_dir)[SA_ID]
    large = _large(sa)
    by_name = {p["dog_name"]: p["draw_number"] for p in large["participants"]}
    assert by_name == {"Alpha": 2, "Bravo": 1}
    # Bracket wird direkt beim Speichern der Losnummern gebaut (Portal-Live).
    r1 = [m for m in large["matchups"] if m["round_no"] == 1 and m["matchup_type"] == "winner"]
    assert len(r1) == 1
    pid = {p["id"]: p["dog_name"] for p in large["participants"]}
    # Losnr 1 (Bravo) gegen Losnr 2 (Alpha).
    assert {pid[r1[0]["a_id"]], pid[r1[0]["b_id"]]} == {"Alpha", "Bravo"}


def test_derive_run_stepwise_appends_across_events(client, tmp_path):
    data_dir = str(tmp_path)

    # Lauf 0 = Tunnellauf (zieht aus dem Fr-Event) -> Alpha, Bravo
    r = client.post(f"/ko-cup/config/{SA_ID}",
                    data={"action": "derive_run", "run_index": "0"})
    assert r.status_code == 302
    sa = _load(data_dir)[SA_ID]
    large = _large(sa)
    assert {p["dog_name"] for p in large["participants"]} == {"Alpha", "Bravo"}

    # Losnummern fuer die ersten beiden vergeben (draw_remaining)
    client.post(f"/ko-cup/final/{SA_ID}/{large['id']}",
                data={"action": "draw_remaining"})
    sa = _load(data_dir)[SA_ID]
    large = _large(sa)
    assert sorted(p["draw_number"] for p in large["participants"]) == [1, 2]

    # Lauf 1 = Agility -> Alpha schon quali -> Delta rueckt nach, ANGEHAENGT
    client.post(f"/ko-cup/config/{SA_ID}",
                data={"action": "derive_run", "run_index": "1"})
    sa = _load(data_dir)[SA_ID]
    large = _large(sa)
    by_name = {p["dog_name"]: p for p in large["participants"]}
    assert set(by_name) == {"Alpha", "Bravo", "Delta"}
    # alte Losnummern intakt, Delta noch unglost
    assert by_name["Delta"]["draw_number"] is None
    assert sorted(p["draw_number"] for p in large["participants"]
                  if p["draw_number"] is not None) == [1, 2]

    # draw_remaining lost nur Delta -> naechste freie Nummer 3
    client.post(f"/ko-cup/final/{SA_ID}/{large['id']}",
                data={"action": "draw_remaining"})
    sa = _load(data_dir)[SA_ID]
    large = _large(sa)
    by_name = {p["dog_name"]: p for p in large["participants"]}
    assert by_name["Delta"]["draw_number"] == 3
    assert sorted(p["draw_number"] for p in large["participants"]) == [1, 2, 3]
    # Nach dem Nachlosen ist das Bracket aktuell (3 Finalisten -> Runde 1 vorhanden).
    assert any(m["round_no"] == 1 for m in large["matchups"])


def test_autobuild_skips_when_results_entered():
    """Schutz: sobald ein Duell echte Ergebnisdaten hat, baut ein erneuter
    Draw das Bracket NICHT neu (sonst gingen Live-Resultate verloren)."""
    import ko_cup
    parts = [
        {"id": "p1", "dog_name": "Alpha", "draw_number": 1},
        {"id": "p2", "dog_name": "Bravo", "draw_number": 2},
    ]
    final = {"participants": parts, "matchups": []}
    assert kc._autobuild_bracket(final) is True
    old_ids = [m["id"] for m in final["matchups"]]
    # Ergebnis erfassen -> Lauf hat eine Zeit.
    r1 = next(m for m in final["matchups"] if m["round_no"] == 1)
    r1["a"]["run1"]["time"] = 20.0
    assert kc._final_has_entries(final) is True
    assert kc._autobuild_bracket(final) is False
    # Matchup-IDs unverändert -> Bracket (und Resultat) blieb erhalten.
    assert [m["id"] for m in final["matchups"]] == old_ids
