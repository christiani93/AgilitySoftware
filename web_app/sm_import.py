"""
TKAMO-SM CSV-Import
===================
Liest einen SportyDog-Resultat-Export (TKAMO-Agility-Schweizermeisterschaft) und
baut daraus SM-Läufe (`sm_run_type`) für `sm_qualification.calculate_sm_qualification`.

SportyDog exportiert den SM-Tag als ZWEI Dateien:
  - **Quali** (Samstag): volles Feld, je Kategorie 1 Agility + 1 Jumping.
  - **Final** (Sonntag): nur Qualifizierte (Teilmenge), je Kategorie 1 Agility + 1 Jumping.
Quali/Final ist NICHT pro Zeile markiert → die PHASE wird pro Datei beim Import gewählt
(Samstag=quali, Sonntag=final). Das Datum taugt nicht (beide Dateien tragen dasselbe Datum).

**Positionsbasiert geparst** (nicht per DictReader): Die Header-Zeile von SportyDog ist
unzuverlässig — beim TKAMO-SM-2024-Export nennt sie nur 20 Spalten (ab „Lizenznummer"),
während die Datenzeilen 25 Felder in fester Reihenfolge tragen (Turniernummer zuerst,
Geraetezahl in der Mitte, ASMV-Spalten am Ende). Die Datenreihenfolge ist stabil; die
Spaltennamen sind es nicht. Format: cp1252, Trenner ';'. Fehler/Verweigerungen stehen in
PUNKTEN (Anzahl × 5) → fürs result-Dict durch 5 geteilt (= Anzahl), wie beim BCCS-Import.
"""
import csv

# Feste 0-basierte Spaltenpositionen einer SportyDog-Resultat-Datenzeile.
COL = {
    "turnier": 0, "lizenz": 1, "hundename": 2, "hundefuehrer": 3, "club": 4,
    "kategorie": 5, "klasse": 6, "rang": 7, "laufzeit": 8, "tempo": 9,
    "fehler": 10, "verweigerungen": 11, "zeitfehler": 12, "gesamtfehler": 13,
    "dis": 14, "lauf": 15, "richter": 16, "parcours": 17, "geraete": 18,
    "sct": 19, "mct": 20, "datum": 21,
}

CATEGORIES = ["Large", "Intermediate", "Medium", "Small"]
LAUFARTEN = ("Agility", "Jumping")

# Phase × Laufart → sm_run_type (vgl. sm_qualification.SM_RUN_TYPES; Quali-Präfix "qual").
_RUN_TYPE = {
    ("quali", "Agility"): "qual_agility",
    ("quali", "Jumping"): "qual_jumping",
    ("final", "Agility"): "final_agility",
    ("final", "Jumping"): "final_jumping",
}


def _num(s, default=0.0):
    try:
        return float(str(s).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def _cell(row, key):
    idx = COL[key]
    return row[idx].strip() if len(row) > idx else ""


def _decode(data) -> str:
    if isinstance(data, bytes):
        return data.decode("cp1252")
    return data


def _entry(row, start_no):
    dis = _cell(row, "dis") or None
    handler = _cell(row, "hundefuehrer")
    parts = handler.rsplit(" ", 1)
    return {
        "Startnummer":  start_no,
        "Lizenznummer": _cell(row, "lizenz"),
        "Hundename":    _cell(row, "hundename"),
        "Vorname":      parts[0] if len(parts) > 1 else handler,
        "Nachname":     parts[-1] if len(parts) > 1 else "",
        "Kategorie":    _cell(row, "kategorie"),
        "Klasse":       _cell(row, "klasse"),
        "result": {
            "zeit":             _num(_cell(row, "laufzeit")) or None,
            "fehler":           int(_num(_cell(row, "fehler")) // 5),          # Punkte → Anzahl
            "verweigerungen":   int(_num(_cell(row, "verweigerungen")) // 5),
            "disqualifikation": dis,
        },
    }


def parse_sm_result_csv(data, phase: str) -> list[dict]:
    """Parst einen SportyDog-Resultat-Export in SM-Läufe.

    `phase`: 'quali' (Samstag) oder 'final' (Sonntag) — bestimmt `sm_run_type`/`is_final`.
    Returns: Liste von Lauf-Dicts (je Kategorie × Laufart ein Lauf), startklar für
    `recalc_and_store` + `calculate_sm_qualification`.
    """
    phase = (phase or "").strip().lower()
    if phase not in ("quali", "final"):
        raise ValueError(f"phase muss 'quali' oder 'final' sein, nicht {phase!r}")

    text = _decode(data)
    rows = list(csv.reader(text.splitlines(), delimiter=";"))
    data_rows = rows[1:] if rows else []   # erste Zeile = (unzuverlässiger) Header

    groups: dict = {}
    for row in data_rows:
        if len(row) <= COL["lauf"]:
            continue
        if not _cell(row, "lizenz"):
            continue
        kat = _cell(row, "kategorie")
        lauf = _cell(row, "lauf")
        if kat not in CATEGORIES or lauf not in LAUFARTEN:
            continue
        groups.setdefault((kat, lauf), []).append(row)

    runs = []
    for (kat, lauf), group_rows in sorted(groups.items()):
        first = group_rows[0]
        runs.append({
            "id":          f"sm_{phase}_{kat}_{lauf}".lower(),
            "kategorie":   kat,
            "klasse":      _cell(first, "klasse") or "3",
            "laufart":     lauf,
            "sm_run_type": _RUN_TYPE[(phase, lauf)],
            "is_final":    phase == "final",
            "laufdaten": {
                "parcours_laenge":    _num(_cell(first, "parcours")),
                "anzahl_hindernisse": int(_num(_cell(first, "geraete"))),
            },
            "entries": [_entry(row, i) for i, row in enumerate(group_rows, 1)],
        })
    return runs


def build_sm_event_from_csvs(quali_data, final_data=None, *, event_id="SM_IMPORT",
                             bezeichnung="TKAMO-SM (CSV-Import)", datum=None) -> dict:
    """Baut ein vollständiges SM-Event-Dict aus Quali- (+ optional Final-) CSV."""
    runs = parse_sm_result_csv(quali_data, "quali")
    if final_data is not None:
        runs += parse_sm_result_csv(final_data, "final")
    return {
        "id":                event_id,
        "Bezeichnung":       bezeichnung,
        "Datum":             datum or "",
        "Veranstaltungsart": "SM Einzel",
        "runs":              runs,
        "sm_config":         {},
    }
