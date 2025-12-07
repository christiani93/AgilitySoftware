import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
WEB_APP_DIR = os.path.join(ROOT_DIR, 'web_app')
if WEB_APP_DIR not in sys.path:
    sys.path.insert(0, WEB_APP_DIR)

from utils import _calculate_run_results  # noqa: E402


def test_sct_mct_rounding():
    run = {
        "klasse": "2",
        "laufart": "Agility",
        "laufdaten": {"parcours_laenge": "150"}
    }
    settings = {"sct_factors": {"Agility": {"2": 3.5}}}

    _calculate_run_results(run, settings)

    ld = run["laufdaten"]

    assert ld["standardzeit_sct_berechnet"] == 43  # 150 / 3.5 = 42.857 -> 43
    assert ld["maximalzeit_mct_berechnet"] == 60   # 150 / 2.5 = 60


def test_timefaults():
    run = {
        "klasse": "2",
        "laufart": "Agility",
        "laufdaten": {"parcours_laenge": "150"},
        "entries": [
            {"lizenz": "A123", "zeit": "43.20", "fehler": 0, "verweigerungen": 0, "result": {
                "zeit": "43.20", "fehler": 0, "verweigerungen": 0
            }}
        ]
    }
    settings = {"sct_factors": {"Agility": {"2": 3.5}}}

    results = _calculate_run_results(run, settings)

    entry = results[0]

    assert entry["zeit_total"] == 43.20
    assert entry["fehler_zeit"] == 0.20  # SCT rounded 43
    assert entry["fehler_total"] == 0.20


def test_mct_exceed():
    run = {
        "klasse": "2",
        "laufart": "Agility",
        "laufdaten": {"parcours_laenge": "150"},
        "entries": [
            {"lizenz": "B999", "zeit": "70.00", "fehler": 0, "verweigerungen": 0, "result": {
                "zeit": "70.00", "fehler": 0, "verweigerungen": 0
            }}
        ]
    }
    settings = {"sct_factors": {"Agility": {"2": 3.5}}}

    results = _calculate_run_results(run, settings)
    entry = results[0]

    assert entry["fehler_total"] == 999


def test_empty_values_safe():
    run = {
        "klasse": "1",
        "laufart": "Agility",
        "laufdaten": {
            "parcours_laenge": "",
            "standardzeit_sct": "",
            "geschwindigkeit": ""
        },
        "entries": []
    }
    settings = {}

    _calculate_run_results(run, settings)
