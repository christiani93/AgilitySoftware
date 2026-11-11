"""
SWG-R-12: Der TKAMO-Export darf eine Kategorie/Klasse nur hochladen, wenn alle
gestarteten Teams ein Resultat oder einen DIS/ABR-Vermerk haben. `_tkamo_run_status`
klassifiziert jeden Lauf; die Export-Route blockiert unvollständige Läufe.
"""
from blueprints.routes_print import _tkamo_run_status


def _run(laufart, entries, klasse="1"):
    return {
        "laufart": laufart,
        "kategorie": "Large",
        "klasse": klasse,
        # Klasse 1: SCT vom Richter vorgegeben → deterministisch ohne Feldberechnung.
        "laufdaten": {"standardzeit_sct": 40, "parcours_laenge": 100},
        "entries": entries,
    }


def _res(zeit=None, dis=None):
    r = {}
    if zeit is not None:
        r["zeit"] = zeit
    if dis is not None:
        r["disqualifikation"] = dis
    return {"Lizenznummer": "x", "result": r}


def _no_result():
    # Team auf der Startliste, aber noch kein Resultat erfasst → 'N/A'.
    return {"Lizenznummer": "y"}


def test_complete_run_all_results():
    run = _run("Agility", [_res(zeit=38), _res(zeit=41)])
    assert _tkamo_run_status(run, {}) == ("complete", 0)


def test_incomplete_run_one_missing():
    run = _run("Agility", [_res(zeit=38), _no_result()])
    assert _tkamo_run_status(run, {}) == ("incomplete", 1)


def test_not_started_run_no_results():
    run = _run("Jumping", [_no_result(), _no_result()])
    assert _tkamo_run_status(run, {}) == ("not_started", 2)


def test_skip_non_reportable_laufart():
    run = _run("KO-Cup", [_res(zeit=38)])
    assert _tkamo_run_status(run, {}) == ("skip", 0)


def test_dns_does_not_block():
    # DNS = nicht gestartet, zählt nicht als fehlendes Resultat.
    run = _run("Agility", [_res(zeit=38), _res(dis="DNS")])
    assert _tkamo_run_status(run, {}) == ("complete", 0)


def test_dis_counts_as_done():
    run = _run("Agility", [_res(zeit=38), _res(dis="DIS")])
    assert _tkamo_run_status(run, {}) == ("complete", 0)


def test_dis_plus_missing_is_incomplete():
    run = _run("Agility", [_res(dis="DIS"), _no_result()])
    assert _tkamo_run_status(run, {}) == ("incomplete", 1)


def test_abr_counts_as_done():
    run = _run("Agility", [_res(zeit=38), _res(dis="ABR")])
    assert _tkamo_run_status(run, {}) == ("complete", 0)
