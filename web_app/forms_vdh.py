# forms_vdh.py
"""Daten für das VDH-Formular "Bestätigung für Auslandsergebnisse" (DE).

Für deutsche Starter (Lizenz-Ländercode DEU/GER) an Schweizer Turnieren, damit das
hier erlaufene Resultat in Deutschland (VDH) als Qualifikation/Leistung anerkannt
wird. Pflicht seit 01.01.2025: ein vom Leistungsrichter unterschriebenes
VDH-Formular je Auslandsergebnis.

Anders als beim FR-CNEAC-Formular (PDF-Overlay auf einer offiziellen Blanko-Vorlage)
wird dieses Formular als HTML-Druckseite gerendert — es gibt keine offizielle
Blanko-PDF-Vorlage. Das Layout bildet die Felder des Originalformulars nach
(zweisprachig DE/EN). Alle Werte sind vorbefüllt, soweit vorhanden; fehlende Felder
bleiben leer und können handschriftlich ergänzt werden. Die Richter-Unterschrift
erfolgt immer per Hand.

Das Formular hat je Lauf einen eigenen Bogen (ein Resultat pro Blatt, wie im
Original), weil der Richter jedes Ergebnis einzeln bestätigt. Für einen Starter mit
mehreren Läufen am Event werden entsprechend mehrere Bögen erzeugt.
"""
from utils import _load_data, _load_settings, _calculate_run_results, resolve_judge_name

# Lauf-Kürzel auf dem Original-Formular (Ankreuzfeld "Lauf / Run").
# Hinweis: J1 existiert auf dem Formular nicht.
RUN_CODES = ["A1", "A2", "J2", "A3", "J3"]
# Leistungsklasse / Grade (Ankreuzfeld). CH-Klasse 1/2/3 == dt. Grade A1/A2/A3.
GRADE_CODES = ["A1", "A2", "A3"]
# Größenklasse / Category (Ankreuzfeld).
CATEGORY_CODES = ["S", "M", "I", "L"]


def _category_letter(kategorie):
    """Small/Medium/Intermediate/Large (oder bereits ein Buchstabe) -> S/M/I/L."""
    s = str(kategorie or "").strip().upper()
    if not s:
        return ""
    return s[0] if s[0] in ("S", "M", "I", "L") else ""


def _grade_code(klasse):
    """CH-Klasse 1/2/3 -> dt. Grade A1/A2/A3 (identisch laut TKAMO/VDH-Praxis)."""
    s = str(klasse or "").strip()
    return f"A{s}" if s in ("1", "2", "3") else ""


def _run_code(laufart, klasse):
    """Agility/Jumping + Klasse -> Formular-Kürzel (A1/A2/J2/A3/J3) oder ''."""
    s = str(klasse or "").strip()
    la = str(laufart or "").strip().lower()
    if la.startswith("agility"):
        code = f"A{s}"
    elif la.startswith("jumping"):
        code = f"J{s}"
    else:
        return ""
    return code if code in RUN_CODES else ""


def _fmt(value, decimals=None):
    if value is None:
        return ""
    if decimals is not None:
        try:
            return f"{float(value):.{decimals}f}"
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _event_country(event):
    """Land des Veranstalters. Bei uns immer die Schweiz."""
    return "Schweiz / Switzerland"


def _total_competitors(event):
    """Teilnehmer insgesamt (alle Leistungs- und Größenklassen zusammen) =
    Anzahl eindeutiger Lizenzen über alle Läufe. Das Formular bestätigt, dass
    der Wettbewerb insgesamt mindestens 40 Teilnehmer hatte."""
    lics = set()
    for run in event.get("runs", []) or []:
        for entry in run.get("entries", []) or []:
            lic = entry.get("Lizenznummer")
            if lic:
                lics.add(str(lic))
    return len(lics)


def collect_vdh_sheets(event, lizenznummer):
    """Liefert (header, sheets) für das VDH-Formular eines Starters.

    header: gemeinsame Kopfdaten (Hund, Hundeführer, Wettbewerb).
    sheets: je ein Dict pro Lauf des Starters (ein Resultat-Bogen pro Lauf).
    """
    lizenznummer = str(lizenznummer)
    settings = _load_settings()
    judges = _load_data("judges.json")
    dogs_map = {d.get("Lizenznummer"): d for d in _load_data("dogs.json")}
    handlers_map = {h.get("id"): h for h in _load_data("handlers.json")}
    clubs_map = {str(c.get("nummer")): c.get("name", "") for c in _load_data("clubs.json")}

    dog = dogs_map.get(lizenznummer, {})
    handler = handlers_map.get(dog.get("Hundefuehrer_ID"), {})

    # Anzeige-Werte bevorzugt aus den Entries ziehen (sind event-aktuell).
    handler_name = None
    dog_name = None
    kategorie = dog.get("Kategorie")
    for run in event.get("runs", []) or []:
        for entry in run.get("entries", []) or []:
            if str(entry.get("Lizenznummer")) == lizenznummer:
                handler_name = handler_name or entry.get("Hundefuehrer")
                dog_name = dog_name or entry.get("Hundename")
                kategorie = kategorie or entry.get("Kategorie")

    if not handler_name:
        handler_name = f"{handler.get('Vorname', '')} {handler.get('Nachname', '')}".strip()

    org_club = clubs_map.get(str(event.get("VeranstalterClubNr")), "")

    header = {
        "dog_name": dog_name or dog.get("Hundename") or "",
        "chip": str(dog.get("Chip", "") or "").strip(),
        "category": _category_letter(kategorie),
        "handler": handler_name or "",
        # N° Leistungsbuch / Licence No. = die Lizenz, mit der angemeldet wurde.
        "licence_no": lizenznummer,
        "team": str(handler.get("Team", "") or "").strip(),
        "competition_club": org_club,
        "competition_country": _event_country(event),
        "date": event.get("Datum") or "",
        "total_competitors": _total_competitors(event),
    }

    sheets = []
    for run in event.get("runs", []) or []:
        entry = next(
            (e for e in run.get("entries", []) or [] if str(e.get("Lizenznummer")) == lizenznummer),
            None,
        )
        if not entry:
            continue
        results = _calculate_run_results(run, settings)
        res = next(
            (r for r in results
             if str(r.get("Lizenznummer")) == lizenznummer
             and r.get("Startnummer") == entry.get("Startnummer")),
            None,
        )
        laufart = run.get("laufart") or ""
        klasse = run.get("klasse")
        laufdaten = run.get("laufdaten", {}) or {}
        parcours = laufdaten.get("parcours_laenge")
        zeit = (res or {}).get("zeit_total")
        dis = (res or {}).get("disqualifikation")
        is_dis = dis in ("DIS", "ABR", "DNS")

        speed = ""
        try:
            if parcours and zeit and float(zeit) > 0 and not is_dis:
                speed = f"{float(parcours) / float(zeit):.2f}"
        except (TypeError, ValueError):
            speed = ""

        sheets.append({
            "run_code": _run_code(laufart, klasse),
            "run_label": run.get("name") or f"{laufart} {klasse}".strip(),
            "grade_code": _grade_code(klasse),
            "ranking": "" if (res is None or is_dis or not res.get("platz")) else _fmt(res.get("platz")),
            "faults": "" if (res is None or is_dis) else _fmt(res.get("fehler_total")),
            "time": dis if is_dis else (_fmt(zeit, 2) if zeit is not None else ""),
            "speed": "" if is_dis else speed,
            "judge": resolve_judge_name(event, run, judges),
        })

    return header, sheets
