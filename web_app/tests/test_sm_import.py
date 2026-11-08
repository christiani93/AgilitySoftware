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


# ── Teilnehmer-Import (Anmeldeliste) ───────────────────────────────────────────

_PART_HEADER = ("Lizenznummer;Rufname;Hundename;Rasse;Geschlecht;Wurfdatum;Kategorie;"
                "Klasse;SHSB;Vereins-Nr.;Verein;Chip-Nr.;Vorname;Name;Strasse;PLZ;Ort;"
                "Telefon;Mobile;E-Mail;Sprache;Land;ACR-Rang;ACR-Punkte;Geburtsdatum;")


def _part_row(lic, rufname, zucht, kat, vorname, name, verein="V", chip="C"):
    return (f"{lic};{rufname};{zucht};Border Collie;Weiblich;2021-01-01;{kat};3;789;"
            f"439;{verein};{chip};{vorname};{name};Str 1;6000;Ort;;079;a@b.ch;d;SUI;10;500;1990-01-01;")


def _part_csv(*rows):
    return "\n".join([_PART_HEADER, *rows])


def test_parse_participants_fields_and_dedup():
    text = _part_csv(
        _part_row("16105", "Nayhra", "O Nayhra from Elly", "Large", "Annette", "Ogierman"),
        _part_row("16307", "Eddy", "Shadow of Aire", "Large", "Philippe", "Cottet"),
        _part_row("16307", "Eddy", "Shadow of Aire", "Large", "Philippe", "Cottet"),  # Dublette
    )
    parts = sm_import.parse_sm_participants(text)
    assert len(parts) == 2                       # Dublette zusammengeführt
    p = parts[0]
    assert p["Hundename"] == "Nayhra"            # Rufname = Anzeigename
    assert p["Zuchtname"] == "O Nayhra from Elly"
    assert p["Handler"] == "Annette Ogierman"
    assert p["Kategorie"] == "Large"


def test_parse_participants_utf8_bom_bytes():
    """Regression: Die Anmeldeliste kommt als UTF-8 MIT BOM. Hart-cp1252-Dekodieren
    verfälschte den Spaltenkopf (ï»¿Lizenznummer) → 0 Zeilen importiert. _decode muss
    das BOM schlucken und Umlaute korrekt lesen."""
    text = _part_csv(_part_row("14848", "Hope", "Honolulu", "Intermediate", "Petra", "Häusermann"))
    raw = b"\xef\xbb\xbf" + text.encode("utf-8")
    parts = sm_import.parse_sm_participants(raw)
    assert len(parts) == 1
    assert parts[0]["Lizenznummer"] == "14848"
    assert parts[0]["Nachname"] == "Häusermann"


def test_parse_participants_cp1252_bytes_fallback():
    """SportyDog-/Alt-Export in cp1252 (kein gültiges UTF-8 bei Umlauten) muss weiter gehen."""
    text = _part_csv(_part_row("222", "Zoom", "Zuchtname", "Large", "Jürg", "Müller"))
    raw = text.encode("cp1252")
    parts = sm_import.parse_sm_participants(raw)
    assert len(parts) == 1
    assert parts[0]["Vorname"] == "Jürg" and parts[0]["Nachname"] == "Müller"


def test_build_event_from_participants_structure():
    text = _part_csv(
        _part_row("1", "A", "AA", "Large", "V", "N"),
        _part_row("2", "B", "BB", "Large", "V", "N"),
        _part_row("3", "C", "CC", "Small", "V", "N"),
    )
    event, stats = sm_import.build_sm_event_from_participants(text)
    assert stats["_total"] == 3
    assert stats["Large"] == 2 and stats["Small"] == 1
    # Je Kategorie 2 Quali (gefüllt) + 2 Final (leer).
    large_quali = [r for r in event["runs"] if r["kategorie"] == "Large" and not r["is_final"]]
    assert len(large_quali) == 2
    assert all(len(r["entries"]) == 2 for r in large_quali)
    large_final = [r for r in event["runs"] if r["kategorie"] == "Large" and r["is_final"]]
    assert len(large_final) == 2 and all(len(r["entries"]) == 0 for r in large_final)
    # Entries ohne Startnummer/Ergebnis.
    e = large_quali[0]["entries"][0]
    assert e["Startnummer"] is None and "result" not in e


def test_qualification_no_results_does_not_crash():
    """Regression: Nach reinem Teilnehmer-Import (noch KEINE Resultate) leitet die
    Import-Route direkt aufs SM-Dashboard weiter → calculate_sm_qualification lief in
    None+None (kombi_parcours aus leerem fehler_parcours). Darf nicht mehr crashen,
    und ein gesetzter Titelverteidiger muss als is_defending markiert sein."""
    from sm_qualification import calculate_sm_qualification
    text = _part_csv(
        _part_row("16046", "Pete", "Feel the difference", "Large", "Yannick", "Boutellier"),
        _part_row("777", "Zoom", "ZZ", "Large", "Bea", "Keller"),
    )
    event, _ = sm_import.build_sm_event_from_participants(text)
    event["sm_config"] = {"Large": {"defending_champion": {"license": "16046"}}}
    sm_data = calculate_sm_qualification(event)   # darf NICHT werfen
    large = sm_data["Large"]
    champ = next(r for r in large["final_list"] if r["license"] == "16046")
    assert champ["is_defending"] is True


# ── Startnummern-Zuordnung ──────────────────────────────────────────────────

def _event_two_runs():
    return {
        "id": "E1",
        "runs": [
            {"id": "r1", "entries": [
                {"Lizenznummer": "111", "Startnummer": None},
                {"Lizenznummer": "222", "Startnummer": None},
            ]},
            {"id": "r2", "entries": [
                {"Lizenznummer": "111", "Startnummer": None},
            ]},
        ],
    }


def test_apply_startnumbers_sets_event_wide():
    ev = _event_two_runs()
    stats = sm_import.apply_sm_startnumbers(ev, "Lizenznummer;Startnummer\n111;7\n222;8\n")
    assert stats["matched"] == 2
    assert stats["unmatched_licenses"] == []
    # Lizenz 111 in BEIDEN Läufen gesetzt.
    nrs = {e["Startnummer"] for run in ev["runs"] for e in run["entries"] if e["Lizenznummer"] == "111"}
    assert nrs == {"7"}
    r1 = ev["runs"][0]["entries"]
    assert next(e for e in r1 if e["Lizenznummer"] == "222")["Startnummer"] == "8"


def test_apply_startnumbers_reports_unmatched_and_comma_delimiter():
    ev = _event_two_runs()
    stats = sm_import.apply_sm_startnumbers(ev, "111,7\n999,99\n")
    assert stats["matched"] == 1
    assert stats["unmatched_licenses"] == ["999"]


def test_apply_startnumbers_skips_invalid_rows():
    ev = _event_two_runs()
    stats = sm_import.apply_sm_startnumbers(ev, "111;abc\n222;8\n")
    assert stats["unknown_rows"] == 1
    assert stats["matched"] == 1


def test_entries_are_independent_copies_per_run():
    text = _part_csv(_part_row("1", "A", "AA", "Large", "V", "N"))
    event, _ = sm_import.build_sm_event_from_participants(text)
    quali = [r for r in event["runs"] if r["kategorie"] == "Large" and not r["is_final"]]
    quali[0]["entries"][0]["Startnummer"] = 5
    assert quali[1]["entries"][0]["Startnummer"] is None  # nicht dieselbe Referenz
