"""
Integrationstest für das VDH-Formular "Bestätigung für Auslandsergebnisse"
(HTML-Druckseite, ``GET /print/vdh_formulaire/<event_id>/<lizenznummer>``).

Deckt ab: Erkennung deutscher Starter (Ländercode DEU) in der Auswahlliste,
Vorbefüllung von Kopf- und Ergebnisdaten, Grade/Kategorie/Lauf-Kürzel-Mapping,
DIS blendet Zeit-/Fehlerwerte sinnvoll (DIS statt Sentinel-999) ein.
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


def _laufdaten(laenge=150, hindernisse=18):
    return {
        "parcours_laenge": laenge,
        "anzahl_hindernisse": hindernisse,
        "standardzeit_sct_gerundet": 50,
        "maximalzeit_mct_gerundet": 75,
    }


def _event():
    return {
        "id": EVENT_ID,
        "Bezeichnung": "Test-Turnier",
        "Datum": "2026-10-10",
        "VeranstalterClubNr": "99",
        "runs": [
            {
                "id": "run_agi_3", "laufart": "Agility", "kategorie": "Large", "klasse": "3",
                "judge_id": "j1", "laufdaten": _laufdaten(),
                "entries": [
                    {"Startnummer": 7, "Hundefuehrer": "Max Mustermann", "Hundename": "Bello",
                     "Lizenznummer": "DEU-5001", "Kategorie": "Large", "Klasse": "3",
                     "result": {"zeit": 48.0, "fehler": 0, "verweigerungen": 0, "disqualifikation": None}},
                    # Zweiter (CH-)Starter, nur damit Teilnehmerzahl > 1 ist.
                    {"Startnummer": 8, "Hundefuehrer": "Hans Meier", "Hundename": "Rex",
                     "Lizenznummer": "12345", "Kategorie": "Large", "Klasse": "3",
                     "result": {"zeit": 46.0, "fehler": 0, "verweigerungen": 0, "disqualifikation": None}},
                ],
            },
            {
                "id": "run_jmp_3", "laufart": "Jumping", "kategorie": "Large", "klasse": "3",
                "judge_id": "j1", "laufdaten": _laufdaten(laenge=160, hindernisse=16),
                "entries": [
                    {"Startnummer": 7, "Hundefuehrer": "Max Mustermann", "Hundename": "Bello",
                     "Lizenznummer": "DEU-5001", "Kategorie": "Large", "Klasse": "3",
                     "result": {"zeit": 30.0, "fehler": 0, "verweigerungen": 0, "disqualifikation": "DIS"}},
                ],
            },
        ],
    }


@pytest.fixture
def app_and_dir(tmp_path, monkeypatch):
    data_dir = str(tmp_path)
    monkeypatch.setenv("AGILITY_DATA_DIR", data_dir)
    with open(os.path.join(data_dir, "dogs.json"), "w", encoding="utf-8") as f:
        json.dump([{"Lizenznummer": "DEU-5001", "Hundename": "Bello", "Rasse": "Border Collie",
                    "Hundefuehrer_ID": "h1", "Kategorie": "Large", "Chip": "276098100123456",
                    "Leistungsbuch": "K-33333"}], f)
    with open(os.path.join(data_dir, "handlers.json"), "w", encoding="utf-8") as f:
        json.dump([{"id": "h1", "Vorname": "Max", "Nachname": "Mustermann", "Vereinsnummer": ""}], f)
    with open(os.path.join(data_dir, "clubs.json"), "w", encoding="utf-8") as f:
        json.dump([{"nummer": "99", "name": "LyTiWee"}], f)
    with open(os.path.join(data_dir, "judges.json"), "w", encoding="utf-8") as f:
        json.dump([{"id": "j1", "firstname": "Elpida", "lastname": "Ismael"}], f)
    with open(os.path.join(data_dir, "events.json"), "w", encoding="utf-8") as f:
        json.dump([_event()], f, ensure_ascii=False)

    app = Flask(__name__, template_folder=os.path.join(WEB_APP_PATH, "templates"))
    app.secret_key = "test"
    app.jinja_env.filters["format_date"] = lambda d: d
    app.jinja_env.globals["_"] = lambda s: s
    app.register_blueprint(rp.print_bp)
    return app, data_dir


def test_vdh_form_renders(app_and_dir):
    app, _ = app_and_dir
    resp = app.test_client().get(f"/print/vdh_formulaire/{EVENT_ID}/DEU-5001")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Bestätigung für Auslandsergebnisse" in html
    assert "Bello" in html
    assert "Max Mustermann" in html
    # Leistungsbuch-Nr. (deutsche VDH-Nummer, NICHT die CH-Lizenz DEU-5001) wird vorbefüllt.
    assert "K-33333" in html
    # Chip-Nummer aus den Stammdaten wird vorbefüllt.
    assert "276098100123456" in html


def test_vdh_list_only_german_starters(app_and_dir, monkeypatch):
    # Die Listen-Seite erbt layout.html (App-globale Context-Processors), daher
    # testen wir nur die Filter-Logik der Route: render_template wird abgefangen
    # und die übergebenen participants geprüft.
    app, _ = app_and_dir
    captured = {}

    def fake_render(template, **ctx):
        captured.update(ctx)
        return ""

    monkeypatch.setattr(rp, "render_template", fake_render)
    with app.test_request_context():
        rp.print_vdh_formulaire_list(EVENT_ID)

    lics = {p["lizenznummer"] for p in captured["participants"]}
    assert lics == {"DEU-5001"}  # CH-Starter "12345" ist raus
    assert captured["participants"][0]["foreign_cc"] == "DEU"


def test_save_vdh_leistungsbuch_persists_to_dog(app_and_dir):
    app, data_dir = app_and_dir
    resp = app.test_client().post(
        f"/print/vdh_formulaire/{EVENT_ID}/DEU-5001/leistungsbuch",
        json={"leistungsbuch": "K-99999"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    with open(os.path.join(data_dir, "dogs.json"), encoding="utf-8") as f:
        dogs = json.load(f)
    assert dogs[0]["Leistungsbuch"] == "K-99999"


def test_save_vdh_leistungsbuch_404_for_unknown_dog(app_and_dir):
    app, _ = app_and_dir
    resp = app.test_client().post(
        f"/print/vdh_formulaire/{EVENT_ID}/NOPE/leistungsbuch",
        json={"leistungsbuch": "K-1"},
    )
    assert resp.status_code == 404


def test_vdh_404_for_unknown_event(app_and_dir):
    app, _ = app_and_dir
    resp = app.test_client().get("/print/vdh_formulaire/nope/DEU-5001")
    assert resp.status_code == 404


def test_collect_sheets_mapping_and_dis(app_and_dir):
    import forms_vdh
    ev = _event()
    header, sheets = forms_vdh.collect_vdh_sheets(ev, "DEU-5001")
    assert header["dog_name"] == "Bello"
    assert header["handler"] == "Max Mustermann"
    assert header["category"] == "L"
    # Leistungsbuch-Nr. (deutsche VDH-Nummer), NICHT die CH-Lizenz "DEU-5001".
    assert header["licence_no"] == "K-33333"
    assert header["competition_club"] == "LyTiWee"
    assert header["total_competitors"] == 2  # DEU-5001 + 12345

    by_code = {s["run_code"]: s for s in sheets}
    assert set(by_code) == {"A3", "J3"}
    # Grade = CH-Klasse 3 -> A3.
    assert by_code["A3"]["grade_code"] == "A3"
    # Sauberer Agility-Lauf: Platz gesetzt, Fehler 0, Speed berechnet.
    assert by_code["A3"]["ranking"] != ""
    assert by_code["A3"]["speed"] != ""
    # DIS-Jumping: Zeit zeigt "DIS", kein Sentinel-999, kein Speed.
    assert by_code["J3"]["time"] == "DIS"
    assert by_code["J3"]["faults"] == ""
    assert by_code["J3"]["speed"] == ""
    assert by_code["J3"]["ranking"] == ""
