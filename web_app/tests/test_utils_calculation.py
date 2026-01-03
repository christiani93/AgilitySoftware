import math

from utils import _calculate_run_results


def pytest_approx(value, expected, tol=1e-6):
    """
    Kleine Approx-Hilfsfunktion, um Floats mit Toleranz zu vergleichen,
    ohne pytest.approx importieren zu müssen.
    """
    return abs(value - expected) <= tol


def test_class1_direct_sct_and_mct_dis_logic():
    run = {
        "klasse": "1",
        "laufart": "Agility",
        "laufdaten": {"standardzeit_sct": "40"},
        "entries": [
            {"lizenz": "A", "zeit": "39.99", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
            {"lizenz": "B", "zeit": "40.01", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
            {"lizenz": "C", "zeit": "60.00", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
            {"lizenz": "D", "zeit": "60.01", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
        ],
    }

    results = _calculate_run_results(run, {})
    laufdaten = run.get("laufdaten", {})

    assert laufdaten.get("standardzeit_sct_berechnet") == 40
    assert laufdaten.get("maximalzeit_mct_berechnet") == 60

    res_map = {r.get("lizenz"): r for r in results}
    assert pytest_approx(res_map["B"]["fehler_zeit"], 0.01)
    assert pytest_approx(res_map["C"]["fehler_zeit"], 20.0)
    assert res_map["D"].get("disqualifikation") == "DIS"
    assert res_map["D"].get("fehler_total") == 999


def test_class1_speed_based_sct():
    run = {
        "klasse": "1",
        "laufart": "Jumping",
        "laufdaten": {"parcours_laenge": "150", "geschwindigkeit": "3.60"},
        "entries": [
            {"lizenz": "A", "zeit": "41.99", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
            {"lizenz": "B", "zeit": "42.00", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
            {"lizenz": "C", "zeit": "42.01", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
            {"lizenz": "D", "zeit": "63.01", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
        ],
    }

    results = _calculate_run_results(run, {})
    laufdaten = run.get("laufdaten", {})

    assert laufdaten.get("standardzeit_sct_berechnet") == 42
    assert laufdaten.get("maximalzeit_mct_berechnet") == 63

    res_map = {r.get("lizenz"): r for r in results}
    assert pytest_approx(res_map["A"]["fehler_zeit"], 0.0)
    assert pytest_approx(res_map["C"]["fehler_zeit"], 0.01)
    assert res_map["D"].get("disqualifikation") == "DIS"


def test_class2_sct_from_best_without_dis():
    run = {
        "klasse": "2",
        "laufart": "Agility",
        "laufdaten": {"parcours_laenge": "150"},
        "entries": [
            {"lizenz": "A", "zeit": "34.50", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
            {"lizenz": "B", "zeit": "35.20", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
            {"lizenz": "C", "zeit": "32.00", "fehler": "5", "verweigerungen": "0", "dis_abr": ""},
            {"lizenz": "D", "zeit": "30.00", "fehler": "0", "verweigerungen": "0", "dis_abr": "DIS"},
        ],
    }

    results = _calculate_run_results(run, {})
    laufdaten = run.get("laufdaten", {})

    assert laufdaten.get("standardzeit_sct_berechnet") == 49
    assert laufdaten.get("maximalzeit_mct_berechnet") == 60

    res_map = {r.get("lizenz"): r for r in results}
    assert pytest_approx(res_map["A"]["fehler_zeit"], 0.0)
    assert pytest_approx(res_map["B"]["fehler_zeit"], 0.0)
    assert res_map["C"].get("fehler_total", 0) >= 5
    assert res_map["D"].get("disqualifikation") == "DIS"


def test_class3_jumping_factor_and_timefault_precision():
    run = {
        "klasse": "3",
        "laufart": "Jumping",
        "laufdaten": {"parcours_laenge": "150"},
        "entries": [
            {"lizenz": "A", "zeit": "34.50", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
            {"lizenz": "B", "zeit": "45.01", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
            {"lizenz": "C", "zeit": "50.10", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
        ],
    }

    results = _calculate_run_results(run, {})
    laufdaten = run.get("laufdaten", {})

    assert laufdaten.get("standardzeit_sct_berechnet") == math.ceil(34.50 * 1.3)
    assert laufdaten.get("maximalzeit_mct_berechnet") == math.ceil(150 / 3.0)

    res_map = {r.get("lizenz"): r for r in results}
    assert pytest_approx(res_map["B"]["fehler_zeit"], 0.01)
    assert res_map["C"].get("disqualifikation") == "DIS"


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
