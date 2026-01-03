import math
import os
import sys

# Ensure web_app package is importable when running from repository root
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
WEB_APP_PATH = os.path.join(PROJECT_ROOT, "web_app")
if WEB_APP_PATH not in sys.path:
    sys.path.insert(0, WEB_APP_PATH)

from utils import _calculate_run_results, _to_float


def find_entry(results, lizenz):
    return next(e for e in results if e.get("lizenz") == lizenz)


def test_k1_a_direct_sct_timefaults_and_mct_dis():
    run = {
        "klasse": "1",
        "laufart": "Agility",
        "laufdaten": {"standardzeit_sct": "40"},
        "entries": [
            {"lizenz": "A", "zeit": "39.99", "fehler": "0", "verweigerungen": "0"},
            {"lizenz": "B", "zeit": "40.01", "fehler": "0", "verweigerungen": "0"},
            {"lizenz": "C", "zeit": "60.00", "fehler": "0", "verweigerungen": "0"},
            {"lizenz": "D", "zeit": "60.01", "fehler": "0", "verweigerungen": "0"},
        ],
    }

    results = _calculate_run_results(run, {})

    sct = run["laufdaten"].get("standardzeit_sct_berechnet")
    mct = run["laufdaten"].get("maximalzeit_mct_berechnet")
    assert sct == 40
    assert mct == 60

    entry_b = find_entry(results, "B")
    assert math.isclose(entry_b.get("fehler_zeit", 0), 0.01, rel_tol=1e-6, abs_tol=1e-6)
    assert entry_b.get("disqualifikation") not in ("DIS", "ABR")

    entry_c = find_entry(results, "C")
    assert entry_c.get("disqualifikation") not in ("DIS", "ABR")

    entry_d = find_entry(results, "D")
    assert entry_d.get("disqualifikation") == "DIS"


def test_k1_b_speed_based_sct_and_timefault():
    run = {
        "klasse": "1",
        "laufart": "Jumping",
        "laufdaten": {"parcours_laenge": "150", "geschwindigkeit": "3.6"},
        "entries": [
            {"lizenz": "X", "zeit": "42.01", "fehler": "0", "verweigerungen": "0"},
        ],
    }

    results = _calculate_run_results(run, {})

    sct = run["laufdaten"].get("standardzeit_sct_berechnet")
    mct = run["laufdaten"].get("maximalzeit_mct_berechnet")
    assert sct == 42
    assert mct == 63

    entry = results[0]
    assert math.isclose(entry.get("fehler_zeit", 0), 0.01, rel_tol=1e-6, abs_tol=1e-6)


def _class2_base_run(include_dis=False):
    entries = [
        {"lizenz": "A", "zeit": "34.50", "fehler": "0", "verweigerungen": "0"},
        {"lizenz": "B", "zeit": "35.20", "fehler": "0", "verweigerungen": "0"},
        {"lizenz": "C", "zeit": "32.00", "fehler": "5", "verweigerungen": "0"},
    ]
    if include_dis:
        entries.append({"lizenz": "D", "zeit": "30.00", "fehler": "0", "verweigerungen": "0", "dis_abr": "DIS"})
    return {
        "klasse": "2",
        "laufart": "Agility",
        "laufdaten": {"parcours_laenge": "150"},
        "entries": entries,
    }


def test_k2_a_best_runner_sets_sct_and_mct():
    run = _class2_base_run(include_dis=False)
    results = _calculate_run_results(run, {})

    sct = run["laufdaten"].get("standardzeit_sct_berechnet")
    mct = run["laufdaten"].get("maximalzeit_mct_berechnet")
    assert sct == 49
    assert mct == 60

    entry_a = find_entry(results, "A")
    assert math.isclose(entry_a.get("fehler_zeit", 0), 0.0, rel_tol=1e-6, abs_tol=1e-6)


def test_k2_b_dis_runner_not_used_for_sct():
    run = _class2_base_run(include_dis=True)
    _calculate_run_results(run, {})
    assert run["laufdaten"].get("standardzeit_sct_berechnet") == 49


def _class3_run():
    return {
        "klasse": "3",
        "laufart": "Jumping",
        "laufdaten": {"parcours_laenge": "150"},
        "entries": [
            {"lizenz": "A", "zeit": "34.50", "fehler": "0", "verweigerungen": "0"},
            {"lizenz": "B", "zeit": "35.20", "fehler": "0", "verweigerungen": "0"},
            {"lizenz": "C", "zeit": "32.00", "fehler": "5", "verweigerungen": "0"},
        ],
    }


def test_k3_a_jump_sct_mct_and_timefault():
    run = _class3_run()
    run["entries"].append({"lizenz": "D", "zeit": "45.01", "fehler": "0", "verweigerungen": "0"})

    results = _calculate_run_results(run, {})

    assert run["laufdaten"].get("standardzeit_sct_berechnet") == 45
    assert run["laufdaten"].get("maximalzeit_mct_berechnet") == 50

    entry_d = find_entry(results, "D")
    assert math.isclose(entry_d.get("fehler_zeit", 0), 0.01, rel_tol=1e-6, abs_tol=1e-6)


def test_mct_boundary_dis_trigger():
    run = _class3_run()
    run["laufdaten"]["parcours_laenge"] = "150"
    run["entries"] = [
        {"lizenz": "SAFE", "zeit": "50.00", "fehler": "0", "verweigerungen": "0"},
        {"lizenz": "OVER", "zeit": "50.01", "fehler": "0", "verweigerungen": "0"},
    ]

    results = _calculate_run_results(run, {})

    mct = run["laufdaten"].get("maximalzeit_mct_berechnet")
    assert mct == 50

    safe_entry = find_entry(results, "SAFE")
    assert safe_entry.get("disqualifikation") not in ("DIS", "ABR")

    over_entry = find_entry(results, "OVER")
    assert over_entry.get("disqualifikation") == "DIS"


def test_parse_empty_sct_does_not_raise():
    assert _to_float("", 1.23) == 1.23
    assert _to_float(None, 2.34) == 2.34
