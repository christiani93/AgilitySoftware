import math
from utils import _calculate_run_results


def pytest_approx(value, expected, tol=1e-6):
    """
    Kleine Approx-Hilfsfunktion, ohne pytest.approx zu benötigen.
    """
    return abs(value - expected) <= tol

def pytest_approx(value, expected, tol=1e-6):
    """
    Kleine Approx-Hilfsfunktion, um Floats mit Toleranz zu vergleichen,
    ohne pytest.approx importieren zu müssen.
    """
    return abs(value - expected) <= tol

def test_sct_mct_rounding_class2_agility():
    run = {
        "klasse": "2",
        "laufart": "Agility",
        "laufdaten": {"parcours_laenge": "150"},
        "entries": []
    }
    settings = {"sct_factors": {"Agility": {"2": 3.5}}}

    results = _calculate_run_results(run, settings)
    assert isinstance(results, list)

    ld = run["laufdaten"]
    sct_rounded = ld.get("standardzeit_sct_berechnet")
    mct_rounded = ld.get("maximalzeit_mct_berechnet")

    assert sct_rounded == math.ceil(150 / 3.5)
    assert mct_rounded == math.ceil(150 / 2.5)


def test_timefaults_use_rounded_sct():
    run = {
        "klasse": "2",
        "laufart": "Agility",
        "laufdaten": {"parcours_laenge": "150"},
        "entries": [
            {
                "lizenz": "A123",
                "zeit": "43.20",
                "fehler": "0",
                "verweigerungen": "0",
                "dis_abr": ""
            }
        ]
    }
    settings = {"sct_factors": {"Agility": {"2": 3.5}}}

    results = _calculate_run_results(run, settings)
    entry = results[0]

    assert entry["zeit_total"] == 43.20
    assert pytest_approx(entry["fehler_zeit"], 0.20)
    assert pytest_approx(entry["fehler_total"], 0.20)

    # SCT_rounded = 43 -> 43.20 - 43 = 0.20
    assert pytest_approx(entry["fehler_zeit"], 0.20)
    assert pytest_approx(entry["fehler_total"], 0.20)

def test_mct_exceed_sets_999():
    run = {
        "klasse": "2",
        "laufart": "Agility",
        "laufdaten": {"parcours_laenge": "150"},
        "entries": [
            {
                "lizenz": "B999",
                "zeit": "70.00",
                "fehler": "0",
                "verweigerungen": "0",
                "dis_abr": ""
            }
        ]
    }
    settings = {"sct_factors": {"Agility": {"2": 3.5}}}

    results = _calculate_run_results(run, settings)
    assert len(results) == 1
    entry = results[0]

    assert entry["fehler_total"] == 999
    assert entry["zeit_total"] == 70.00

    for entry in results:
        # Je nach Implementierung kann qualifikation oder fehler_total speziell gesetzt sein,
        # aber es darf kein Crash passieren und die Einträge müssen zurückgegeben werden.
        assert "lizenz" in entry

def test_empty_values_do_not_crash():
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

    results = _calculate_run_results(run, settings)
    assert isinstance(results, list)
