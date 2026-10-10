"""
Integrationstest fuer das CNEAC-Ergebnisformular (Overlay auf der franz.
Originalvorlage, ``GET /print/fr_formulaire/<event_id>/<lizenznummer>``).

Deckt die Kernlogik ab: Zeilenzuordnung nach Klasse (nicht Lauf-Reihenfolge),
DIS/ABR blendet die Sentinel-Fehlerpunkte (999) nicht ein, der
Ausland-Platzhalter-Vereinsname wird nicht mit ausgegeben.
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
                "id": "run_agi_2", "laufart": "Agility", "kategorie": "Large", "klasse": "2",
                "judge_id": "j1",
                "laufdaten": _laufdaten(),
                "entries": [
                    {"Startnummer": 1, "Hundefuehrer": "Arthur Naud", "Hundename": "Haze",
                     "Lizenznummer": "FRA-1001", "Kategorie": "Large", "Klasse": "2",
                     "result": {"zeit": 45.0, "fehler": 0, "verweigerungen": 0, "disqualifikation": "DIS"}},
                ],
            },
            {
                "id": "run_jmp_2", "laufart": "Jumping", "kategorie": "Large", "klasse": "2",
                "judge_id": "j1",
                "laufdaten": _laufdaten(laenge=160, hindernisse=16),
                "entries": [
                    {"Startnummer": 1, "Hundefuehrer": "Arthur Naud", "Hundename": "Haze",
                     "Lizenznummer": "FRA-1001", "Kategorie": "Large", "Klasse": "2",
                     "result": {"zeit": 32.5, "fehler": 1, "verweigerungen": 0, "disqualifikation": None}},
                ],
            },
        ],
    }


@pytest.fixture
def app_and_dir(tmp_path, monkeypatch):
    data_dir = str(tmp_path)
    monkeypatch.setenv("AGILITY_DATA_DIR", data_dir)
    with open(os.path.join(data_dir, "dogs.json"), "w", encoding="utf-8") as f:
        json.dump([{"Lizenznummer": "FRA-1001", "Hundename": "Haze", "Rasse": "Border Collie",
                    "Hundefuehrer_ID": "h1"}], f)
    with open(os.path.join(data_dir, "handlers.json"), "w", encoding="utf-8") as f:
        json.dump([{"id": "h1", "Vereinsnummer": "--- AUSLAND/ ETRANGER/ FOREIGN ---"}], f)
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


def test_fr_formulaire_pdf_download(app_and_dir):
    app, _ = app_and_dir
    resp = app.test_client().get(f"/print/fr_formulaire/{EVENT_ID}/FRA-1001")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data[:4] == b"%PDF"


def test_fr_formulaire_404_for_unknown_event(app_and_dir):
    app, _ = app_and_dir
    resp = app.test_client().get("/print/fr_formulaire/does_not_exist/FRA-1001")
    assert resp.status_code == 404


def test_collect_row_blanks_sentinel_penalty_on_dis(app_and_dir):
    from utils import _load_settings
    import forms_fr
    ev = _event()
    run = ev["runs"][0]  # Agility Kl.2, DIS
    entry = run["entries"][0]
    row = forms_fr._collect_row(ev, run, entry, judges=[{"id": "j1", "firstname": "Elpida", "lastname": "Ismael"}],
                                 settings=_load_settings())
    assert row["temps"] == "DIS"
    assert row["qualif"] == "DIS"
    # Sentinel-Werte (fehler_total=999 etc.) duerfen NICHT auf dem offiziellen
    # Formular auftauchen.
    assert row["pen_total"] == ""
    assert row["pen_parcours"] == ""
    assert row["pen_temps"] == ""


def test_dog_handler_header_blanks_foreign_sentinel_club(app_and_dir):
    import forms_fr
    ev = _event()
    header = forms_fr._dog_and_handler_header(ev, "FRA-1001")
    assert header["club"] == ""
    assert header["chien"] == "Haze"
    assert header["conducteur"] == "Arthur Naud"
