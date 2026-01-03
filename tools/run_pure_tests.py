"""Lightweight CLI runner for pure SCT/MCT/Timefault checks.

Usage:
    python tools/run_pure_tests.py

Returns exit code 0 on success, 1 on first failure.
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_APP_PATH = os.path.join(PROJECT_ROOT, "web_app")
if WEB_APP_PATH not in sys.path:
    sys.path.insert(0, WEB_APP_PATH)

from utils import _calculate_run_results, _to_float  # noqa: E402


def _assert(cond, message):
    if not cond:
        raise AssertionError(message)


def _run_case(name, func):
    print(f"[RUN] {name}…", end=" ")
    func()
    print("OK")


def case_k1_a():
    run = {
        "klasse": "1",
        "laufart": "Agility",
        "laufdaten": {"standardzeit_sct": "40"},
        "entries": [
            {"lizenz": "A", "zeit": "39.99", "fehler": "0", "verweigerungen": "0"},
            {"lizenz": "B", "zeit": "60.01", "fehler": "0", "verweigerungen": "0"},
        ],
    }
    res = _calculate_run_results(run, {})
    _assert(run["laufdaten"].get("standardzeit_sct_berechnet") == 40, "SCT should be 40")
    _assert(run["laufdaten"].get("maximalzeit_mct_berechnet") == 60, "MCT should be 60")
    b_entry = next(r for r in res if r.get("lizenz") == "B")
    _assert(b_entry.get("disqualifikation") == "DIS", "Entry B should be DIS for MCT exceedance")


def case_k3_mct_boundary():
    run = {
        "klasse": "3",
        "laufart": "Jumping",
        "laufdaten": {"parcours_laenge": "150"},
        "entries": [
            {"lizenz": "SAFE", "zeit": "50.00", "fehler": "0", "verweigerungen": "0"},
            {"lizenz": "OVER", "zeit": "50.01", "fehler": "0", "verweigerungen": "0"},
        ],
    }
    res = _calculate_run_results(run, {})
    _assert(run["laufdaten"].get("maximalzeit_mct_berechnet") == 50, "MCT should be 50")
    safe = next(r for r in res if r.get("lizenz") == "SAFE")
    over = next(r for r in res if r.get("lizenz") == "OVER")
    _assert(over.get("disqualifikation") == "DIS", "OVER should be DIS")
    _assert(safe.get("disqualifikation") not in ("DIS", "ABR"), "SAFE should not be DIS")


def case_empty_parse():
    _assert(_to_float("", 1.23) == 1.23, "Empty string should fall back to default")
    _assert(_to_float(None, 2.34) == 2.34, "None should fall back to default")


def main():
    try:
        _run_case("K1-A baseline DIS", case_k1_a)
        _run_case("K3 MCT boundary", case_k3_mct_boundary)
        _run_case("Parse empty SCT", case_empty_parse)
    except AssertionError as exc:
        print(f"FAIL\n  -> {exc}")
        sys.exit(1)
    print("\nAll pure checks passed.")


if __name__ == "__main__":
    main()
