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


# ── Teilnehmer-Import (Anmeldeliste, AOA-Format) ────────────────────────────────
# Anders als der Resultat-Export (oben) hat die Anmeldeliste eine zuverlässige
# Kopfzeile → per Spaltenname gelesen. Enthält KEINE Ergebnisse und KEINE
# Startnummern (letztere kommen später).

def parse_sm_participants(data):
    """Liest eine SM-Anmeldeliste (AOA-Export, ';', cp1252) in Teilnehmer-Dicts.

    Doppelte Lizenznummern werden zusammengeführt (erster Eintrag gewinnt). Returns
    Liste in Eingabereihenfolge (dedupliziert).
    """
    text = _decode(data)
    rows = list(csv.DictReader(text.splitlines(), delimiter=";"))
    seen = {}
    out = []
    for r in rows:
        lic = (r.get("Lizenznummer") or "").strip()
        if not lic or lic in seen:
            continue
        seen[lic] = True
        handler = " ".join(x for x in [(r.get("Vorname") or "").strip(),
                                       (r.get("Name") or "").strip()] if x)
        out.append({
            "Lizenznummer": lic,
            "Hundename":    (r.get("Rufname") or "").strip(),        # Rufname = Anzeigename
            "Zuchtname":    (r.get("Hundename") or "").strip(),      # voller Zwinger-/FCI-Name
            "Rasse":        (r.get("Rasse") or "").strip(),
            "Geschlecht":   (r.get("Geschlecht") or "").strip(),
            "Vorname":      (r.get("Vorname") or "").strip(),
            "Nachname":     (r.get("Name") or "").strip(),
            "Handler":      handler,
            "Kategorie":    (r.get("Kategorie") or "").strip(),
            "Klasse":       (r.get("Klasse") or "").strip(),
            "SHSB":         (r.get("SHSB") or "").strip(),
            "VereinsNr":    (r.get("Vereins-Nr.") or "").strip(),
            "Verein":       (r.get("Verein") or "").strip(),
            "ChipNr":       (r.get("Chip-Nr.") or "").strip(),
            "Land":         (r.get("Land") or "").strip(),
            "Sprache":      (r.get("Sprache") or "").strip(),
            "EMail":        (r.get("E-Mail") or "").strip(),
        })
    return out


def _participant_entry(p):
    """Macht aus einem Teilnehmer einen Lauf-Entry (ohne Ergebnis, ohne Startnummer)."""
    return {
        "Startnummer":  None,                 # kommt später
        "Lizenznummer": p["Lizenznummer"],
        "Hundename":    p["Hundename"],
        "Zuchtname":    p.get("Zuchtname", ""),
        "Rasse":        p.get("Rasse", ""),
        "Vorname":      p["Vorname"],
        "Nachname":     p["Nachname"],
        "Kategorie":    p["Kategorie"],
        "Klasse":       p["Klasse"],
        "Verein":       p.get("Verein", ""),
        "VereinsNr":    p.get("VereinsNr", ""),
        "SHSB":         p.get("SHSB", ""),
        "ChipNr":       p.get("ChipNr", ""),
        "Land":         p.get("Land", ""),
    }


def apply_sm_startnumbers(event: dict, data) -> dict:
    """Setzt Startnummern an allen Entries eines SM-Events anhand einer einfachen
    Zuordnungs-CSV ``Lizenznummer;Startnummer`` (optionale Kopfzeile wird erkannt
    und übersprungen, Trenner ';' oder ','). Wirkt event-weit (alle Läufe), damit
    dieselbe Lizenz überall dieselbe Startnummer trägt.

    Mutiert `event["runs"][*]["entries"][*]["Startnummer"]` in-place. Returns Stats
    ``{"matched": n, "unmatched_licenses": [...], "unknown_rows": n}``.
    """
    text = _decode(data)
    delimiter = ";" if text.count(";") >= text.count(",") else ","
    rows = list(csv.reader(text.splitlines(), delimiter=delimiter))

    mapping: dict[str, str] = {}
    unknown_rows = 0
    for row in rows:
        if len(row) < 2:
            continue
        lic, start_no = row[0].strip(), row[1].strip()
        if not lic or not start_no:
            continue
        if lic.lower() in ("lizenznummer", "lizenz", "license"):
            continue  # Kopfzeile
        if not start_no.lstrip("-").isdigit():
            unknown_rows += 1
            continue
        mapping[lic] = start_no

    event_licenses = {
        str(e.get("Lizenznummer") or "")
        for run in event.get("runs", []) or []
        for e in run.get("entries", []) or []
    }

    matched = 0
    for run in event.get("runs", []) or []:
        for entry in run.get("entries", []) or []:
            lic = str(entry.get("Lizenznummer") or "")
            if lic in mapping:
                entry["Startnummer"] = mapping[lic]

    matched_licenses = event_licenses & set(mapping)
    matched = len(matched_licenses)
    unmatched_licenses = sorted(set(mapping) - event_licenses)

    return {
        "matched": matched,
        "unmatched_licenses": unmatched_licenses,
        "unknown_rows": unknown_rows,
    }


def build_sm_event_from_participants(data, *, event_id="SM_2026",
                                     bezeichnung="TKAMO-SM (Teilnehmer-Import)",
                                     datum=None) -> tuple[dict, dict]:
    """Baut ein SM-Event aus der Anmeldeliste: je Kategorie die beiden Quali-Läufe
    (qual_agility, qual_jumping) mit allen Teilnehmern als Einträge + leere Finalläufe
    (final_jumping, final_agility). Noch OHNE Ergebnisse und OHNE Startnummern.

    Returns (event, stats) — stats = {kategorie: anzahl, ..., "_total": n, "_duplikate": n}.
    """
    participants = parse_sm_participants(data)

    by_cat: dict = {}
    for p in participants:
        by_cat.setdefault(p["Kategorie"], []).append(p)

    runs = []
    stats = {}
    # Feste Kategorie-Reihenfolge (nur vorhandene).
    for cat in CATEGORIES:
        plist = by_cat.get(cat) or []
        if not plist:
            continue
        stats[cat] = len(plist)
        klasse = plist[0]["Klasse"] or "3"
        for phase, laufart in (("quali", "Agility"), ("quali", "Jumping")):
            runs.append({
                "id":          f"sm_{phase}_{cat}_{laufart}".lower(),
                "kategorie":   cat, "klasse": klasse, "laufart": laufart,
                "sm_run_type": _RUN_TYPE[(phase, laufart)], "is_final": False,
                "laufdaten":   {},
                "entries":     [_participant_entry(p) for p in plist],
            })
        for phase, laufart in (("final", "Jumping"), ("final", "Agility")):
            runs.append({
                "id":          f"sm_{phase}_{cat}_{laufart}".lower(),
                "kategorie":   cat, "klasse": klasse, "laufart": laufart,
                "sm_run_type": _RUN_TYPE[(phase, laufart)], "is_final": True,
                "laufdaten":   {}, "entries": [],
            })

    stats["_total"] = len(participants)
    event = {
        "id":                event_id,
        "Bezeichnung":       bezeichnung,
        "Datum":             datum or "",
        "Veranstaltungsart": "SM Einzel",
        "runs":              runs,
        "sm_config":         {},
    }
    return event, stats
