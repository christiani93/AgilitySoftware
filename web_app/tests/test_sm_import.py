"""TKAMO-SM CSV-Import (sm_import.py).

Positionsbasiertes Parsen (header-agnostisch): SportyDog-Resultat-Export, 25 Spalten
feste Reihenfolge (Turniernummer;Lizenznummer;...;Lauf;Richter;Parcourslaenge;Geraetezahl;
Standardzeit;Maximalzeit;Datum;ASMV…). Header-Zeile kann falsch/kurz sein → wird ignoriert.
Fehler/Verweigerungen in Punkten → /5 = Anzahl.
"""
import sm_import


def _row(lic, dog, hf, kat, kl, rang, zeit, fehler, verw, dis, lauf,
         parcours="200", geraete="20"):
    # 25 Felder in fester SportyDog-Reihenfolge (Turniernummer zuerst, ASMV am Ende).
    return ";".join(str(x) for x in [
        "9999", lic, dog, hf, "0", kat, kl, rang, zeit, "5.0", fehler, verw,
        "0.00", "0.00", dis, lauf, "22115", parcours, geraete, "48.00", "84.0",
        "14.09.2024", "", "", "",
    ])


# Bewusst FALSCHER/kurzer Header (wie bei den nachträglichen TKAMO-Exporten) → muss ignoriert werden.
_WRONG_HEADER = "Lizenznummer;Hundename;Hundefuehrer;Club;Kategorie;Klasse;Rang"


def _csv(*rows):
    return "\n".join([_WRONG_HEADER, *rows])


def test_parse_quali_runs_header_agnostic():
    text = _csv(
        _row("111", "Fly", "Anna Meier", "Large", "3", "1", "35.00", "0", "0", "", "Agility"),
        _row("222", "Zoom", "Bea Keller", "Large", "3", "2", "36.00", "5", "0", "", "Agility"),
        _row("111", "Fly", "Anna Meier", "Large", "3", "1", "33.00", "0", "0", "", "Jumping"),
    )
    runs = sm_import.parse_sm_result_csv(text, "quali")
    by_type = {r["sm_run_type"]: r for r in runs}
    assert set(by_type) == {"qual_agility", "qual_jumping"}
    qa = by_type["qual_agility"]
    assert qa["kategorie"] == "Large" and qa["klasse"] == "3"
    assert qa["is_final"] is False
    assert qa["laufdaten"]["parcours_laenge"] == 200.0
    # Lizenz korrekt aus Spalte 1 (trotz falschem Header), nicht die Turniernummer.
    assert {e["Lizenznummer"] for e in qa["entries"]} == {"111", "222"}
    fly = next(e for e in qa["entries"] if e["Lizenznummer"] == "111")
    assert fly["Hundename"] == "Fly"
    assert fly["Vorname"] == "Anna" and fly["Nachname"] == "Meier"


def test_fehler_points_divided_by_five():
    text = _csv(_row("111", "Fly", "A B", "Large", "3", "1", "35.00", "10", "5", "", "Agility"))
    e = sm_import.parse_sm_result_csv(text, "quali")[0]["entries"][0]
    assert e["result"]["fehler"] == 2          # 10 Punkte / 5
    assert e["result"]["verweigerungen"] == 1  # 5 Punkte / 5
    assert e["result"]["zeit"] == 35.00


def test_final_phase_sets_run_type_and_flag():
    text = _csv(_row("111", "Fly", "A B", "Small", "3", "1", "30.00", "0", "0", "", "Jumping"))
    r = sm_import.parse_sm_result_csv(text, "final")[0]
    assert r["sm_run_type"] == "final_jumping"
    assert r["is_final"] is True


def test_dis_carried_into_result():
    text = _csv(_row("333", "Dash", "C D", "Medium", "3", "", "0", "0", "0", "DIS", "Agility"))
    e = sm_import.parse_sm_result_csv(text, "quali")[0]["entries"][0]
    assert e["result"]["disqualifikation"] == "DIS"


def test_build_event_combines_quali_and_final():
    quali = _csv(_row("111", "Fly", "A B", "Large", "3", "1", "35.0", "0", "0", "", "Agility"))
    final = _csv(_row("111", "Fly", "A B", "Large", "3", "1", "40.0", "0", "0", "", "Agility"))
    ev = sm_import.build_sm_event_from_csvs(quali, final)
    assert ev["Veranstaltungsart"] == "SM Einzel"
    types = {r["sm_run_type"] for r in ev["runs"]}
    assert "qual_agility" in types and "final_agility" in types


def test_invalid_phase_raises():
    import pytest
    with pytest.raises(ValueError):
        sm_import.parse_sm_result_csv("x", "bogus")
