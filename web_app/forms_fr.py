# forms_fr.py
"""Ausfüllen des offiziellen CNEAC-Ergebnisformulars (Centrale Canine, FR) als
PDF-Overlay auf der Originalvorlage – für Teilnehmer mit französischer Lizenz.

Koordinaten wurden einmalig gegen die Originalvorlage vermessen
(static/forms/formulaire_resultats_fr.pdf, A4, 2x A5 identisch untereinander,
Y-Versatz zwischen den beiden Hälften = 401.3pt) und sind hier als Konstanten
hinterlegt. Die Vorlage selbst wird nie verändert, nur text-overlayed.

Zeilenzuordnung: Das Formular hat je 3 Zeilen "Agility"/"Jumping" – das
entspricht exakt unseren Klassen 1/2/3 (NICHT Quali-Runden), d.h. ein Hund
mit Klasse 2 landet in Zeile "Agility 2" bzw. "Jumping 2", die anderen
Zeilen bleiben leer.
"""
import os
import pymupdf

from utils import _load_data, _load_settings, recalc_and_store, resolve_judge_name

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "static", "forms", "formulaire_resultats_fr.pdf")

Y_OFFSET_BOTTOM_HALF = 401.3

# Tabellen-Spalten (x0, x1), gemessen an den Rahmenlinien der Vorlage.
COLS = {
    "juge":          (73.4, 168.2),
    "engages":       (168.2, 207.5),
    "longueur":      (207.5, 246.1),
    "obstacles":     (246.1, 289.4),
    "tps":           (289.4, 313.0),
    "tpm":           (313.0, 336.7),
    "temps":         (336.7, 366.0),
    "ms":            (366.0, 401.1),
    "pen_temps":     (401.1, 436.3),
    "pen_parcours":  (436.3, 471.4),
    "pen_total":     (471.4, 506.5),
    "rang":          (506.5, 529.3),
    "qualif":        (529.3, 556.0),
}

# Tabellen-Zeilen (y0, y1) je Klasse, 1-indexiert wie im Formular.
ROWS_AGILITY = {1: (179.3, 202.1), 2: (202.1, 224.9), 3: (224.9, 247.7)}
ROWS_JUMPING = {1: (247.7, 270.4), 2: (270.4, 293.2), 3: (293.2, 316.0)}

# Kopf-Felder: (x_value_start, y_baseline, x_max)
HEADER_FIELDS = {
    "club_organisateur": (98, 86.3, 240),
    "date":              (462, 86.3, 565),
    "chien":             (60, 101.2, 200),
    "race":              (349, 101.2, 480),
    "conducteur":        (79, 116.2, 238),
    "club":              (266, 116.2, 389),
    "n_licence":         (73, 131.2, 167),
    "n_dossard":         (216, 131.2, 301),
    "categorie":         (345, 131.2, 424),
    "classe":            (459, 131.2, 565),
}

TABLE_FONTSIZE = 7
HEADER_FONTSIZE = 8
FONT = "helv"


def _fit_fontsize(text, max_width, start_size):
    size = start_size
    while size > 5.5 and pymupdf.get_text_length(text, fontname=FONT, fontsize=size) > max_width:
        size -= 0.5
    return size


def _draw_left(page, x, y_baseline, text, max_width, fontsize=HEADER_FONTSIZE, dy=0):
    text = str(text or "").strip()
    if not text:
        return
    size = _fit_fontsize(text, max_width, fontsize)
    page.insert_text((x, y_baseline + dy), text, fontname=FONT, fontsize=size, color=(0, 0, 0))


def _draw_centered(page, x0, x1, y_baseline, text, fontsize=TABLE_FONTSIZE, dy=0):
    text = str(text or "").strip()
    if not text:
        return
    width = x1 - x0 - 2
    size = _fit_fontsize(text, width, fontsize)
    text_width = pymupdf.get_text_length(text, fontname=FONT, fontsize=size)
    x = x0 + (x1 - x0 - text_width) / 2
    page.insert_text((x, y_baseline + dy), text, fontname=FONT, fontsize=size, color=(0, 0, 0))


def _fmt_num(value, decimals=None):
    if value is None:
        return ""
    if decimals is not None:
        try:
            return f"{float(value):.{decimals}f}"
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _collect_row(event, run, entry, judges, settings):
    """Berechnet (recalc_and_store) die Resultate des Laufs und liefert die
    Zeilen-Werte für genau diesen Entry zurück. None, falls der Entry im Lauf
    nicht (mehr) existiert."""
    computed = recalc_and_store(run, settings)
    lic = str(entry.get("Lizenznummer"))
    start_no = entry.get("Startnummer")
    result = next(
        (c for c in computed if str(c.get("Lizenznummer")) == lic and c.get("Startnummer") == start_no),
        None,
    )
    laufdaten = run.get("laufdaten", {}) or {}
    parcours_laenge = laufdaten.get("parcours_laenge")
    sct = laufdaten.get("standardzeit_sct_gerundet")
    mct = laufdaten.get("maximalzeit_mct_gerundet")
    engages = len(run.get("entries", []))

    zeit_total = (result or {}).get("zeit_total")
    speed = ""
    try:
        if parcours_laenge and zeit_total and float(zeit_total) > 0:
            speed = f"{float(parcours_laenge) / float(zeit_total):.2f}"
    except (TypeError, ValueError):
        speed = ""

    dis = (result or {}).get("disqualifikation")
    is_dis = dis in ("DIS", "ABR", "DNS")

    return {
        "juge": resolve_judge_name(event, run, judges),
        "engages": engages,
        "longueur": _fmt_num(parcours_laenge),
        "obstacles": _fmt_num(laufdaten.get("anzahl_hindernisse")),
        "tps": _fmt_num(sct),
        "tpm": _fmt_num(mct),
        "temps": dis if is_dis else _fmt_num(zeit_total, 2) if zeit_total is not None else "",
        "ms": "" if is_dis else speed,
        "pen_temps": "" if (result is None or is_dis) else _fmt_num(result.get("fehler_zeit")),
        "pen_parcours": "" if (result is None or is_dis) else _fmt_num(result.get("fehler_parcours")),
        "pen_total": "" if (result is None or is_dis) else _fmt_num(result.get("fehler_total")),
        "rang": "" if (result is None or not result.get("platz")) else _fmt_num(result.get("platz")),
        "qualif": "" if result is None else _fmt_num(result.get("qualifikation")),
    }


def _find_entry_run(event, lizenznummer, laufart, klasse):
    for run in event.get("runs", []) or []:
        if (run.get("laufart") or "") != laufart:
            continue
        if str(run.get("klasse")) != str(klasse):
            continue
        for entry in run.get("entries", []) or []:
            if str(entry.get("Lizenznummer")) == str(lizenznummer):
                return run, entry
    return None, None


def _club_name(nummer):
    if not nummer:
        return ""
    clubs_map = {str(c.get("nummer")): c.get("name", "") for c in _load_data("clubs.json")}
    return clubs_map.get(str(nummer), "")


def _dog_and_handler_header(event, lizenznummer):
    """Holt Chien/Race/Conducteur/Club/N° licence aus dem ersten gefundenen
    Entry des Hundes im Event (Rasse/Verein via dogs.json/handlers.json wie
    bei den übrigen Drucksachen)."""
    dogs_map = {d["Lizenznummer"]: d for d in _load_data("dogs.json")}
    handlers_map = {h["id"]: h for h in _load_data("handlers.json")}
    clubs_map = {str(c.get("nummer")): c.get("name", "") for c in _load_data("clubs.json")}

    dog = dogs_map.get(lizenznummer, {})
    handler = handlers_map.get(dog.get("Hundefuehrer_ID"), {})
    vn = str(handler.get("Vereinsnummer", "") or "").strip()
    verein = clubs_map.get(vn, "")
    if not verein and vn and not vn.isdigit():
        verein = vn
    if verein.strip().upper().startswith("--- AUSLAND"):
        # Sentinel-Freitext für "Ausland, kein konkreter Verein erfasst"
        # (handlers.json Vereinsnummer) - auf dem offiziellen Formular leer lassen.
        verein = ""

    handler_name = None
    dog_name = None
    start_no = None
    for run in event.get("runs", []) or []:
        for entry in run.get("entries", []) or []:
            if str(entry.get("Lizenznummer")) == str(lizenznummer):
                handler_name = handler_name or entry.get("Hundefuehrer")
                dog_name = dog_name or entry.get("Hundename")
                start_no = start_no or entry.get("Startnummer")
    return {
        "chien": dog_name or dog.get("Hundename") or "",
        "race": dog.get("Rasse") or "",
        "conducteur": handler_name or "",
        "club": verein,
        "n_licence": lizenznummer,
        "n_dossard": start_no,
    }


def generate_fr_result_pdf(event, lizenznummer):
    """Füllt das CNEAC-Formular für einen Hund/Teilnehmer in diesem Event aus
    und gibt die PDF-Bytes zurück. Beide A5-Hälften der Seite werden identisch
    befüllt (2 Kopien zum Trennen: Handler + Club/Organisator)."""
    judges = _load_data("judges.json")
    settings = _load_settings()

    header = _dog_and_handler_header(event, lizenznummer)
    header["club_organisateur"] = _club_name(event.get("VeranstalterClubNr"))
    header["date"] = event.get("Datum") or ""
    header["categorie"] = ""
    header["classe"] = ""

    rows_agility, rows_jumping = {}, {}
    for klasse in (1, 2, 3):
        run, entry = _find_entry_run(event, lizenznummer, "Agility", klasse)
        if run:
            rows_agility[klasse] = _collect_row(event, run, entry, judges, settings)
            header["categorie"] = entry.get("Kategorie") or header["categorie"]
            header["classe"] = header["classe"] or str(klasse)
        run, entry = _find_entry_run(event, lizenznummer, "Jumping", klasse)
        if run:
            rows_jumping[klasse] = _collect_row(event, run, entry, judges, settings)
            header["categorie"] = entry.get("Kategorie") or header["categorie"]
            header["classe"] = header["classe"] or str(klasse)

    doc = pymupdf.open(TEMPLATE_PATH)
    page = doc[0]

    for y_offset in (0, Y_OFFSET_BOTTOM_HALF):
        for field, (x, y, max_w) in HEADER_FIELDS.items():
            _draw_left(page, x, y, header.get(field, ""), max_w - x, dy=y_offset)

        for klasse, row in rows_agility.items():
            y0, y1 = ROWS_AGILITY[klasse]
            baseline = y1 - 5
            for col, (x0, x1) in COLS.items():
                _draw_centered(page, x0, x1, baseline, row.get(col, ""), dy=y_offset)

        for klasse, row in rows_jumping.items():
            y0, y1 = ROWS_JUMPING[klasse]
            baseline = y1 - 5
            for col, (x0, x1) in COLS.items():
                _draw_centered(page, x0, x1, baseline, row.get(col, ""), dy=y_offset)

    return doc.tobytes()
