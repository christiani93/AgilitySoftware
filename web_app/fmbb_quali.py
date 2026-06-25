"""
FMBB-WM Agility Quali — Tag-Auswertung
========================================

Reglement / Modus: siehe Memory project_fmbb_quali.md.
Implementations-Plan: project_fmbb_implementation.md.

Anwendungsfall (User-Klarstellung 2026-06-14):
Die FMBB-Quali wird als **2 separate 1-Tages-Auswertungen** durchgeführt.
Die Saison-Wertung (8+2 qualifizieren mit Streichresultaten) macht der
SKBS-Verband — NICHT diese Software.

User-Entscheide 2026-06-14:
- **FMBB-Marker:** explizit pro Anmeldung über `entry["is_fmbb"]` (manueller Flag).
  Bulk-Setzen über `mark_fmbb_by_licenses()` mit einer Liste von Lizenznummern
  (die der Veranstalter von SKBS bekommt). Kein automatischer Rasse-Filter.
- **Punkteformel:** keine im Tool. Wir liefern pro Lauf nur die Rangliste
  (basiert auf `rank` von AgilitySoftware). SKBS macht die Saison-Punkte.

Aktivierung:
`event["fmbb_quali_active"] = True` markiert ein Event als FMBB-Quali-Tag
(Overlay über bestehende Veranstaltungsart, kein eigener Typ). Doppelnutzung
mit SKBS-SM möglich am selben Event.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

# Klassen die FMBB-startberechtigt sind (project_fmbb_quali.md, Reglement)
FMBB_ELIGIBLE_CLASSES = ("2", "3")

# Relevante Lauftypen
FMBB_RUN_TYPES = ("Agility", "Jumping")


# ---------------------------------------------------------------------------
# Public API — Aktivierung & Marker
# ---------------------------------------------------------------------------

def is_fmbb_active(event: dict) -> bool:
    """True wenn der Event als FMBB-Quali-Tag markiert ist."""
    return bool(event.get("fmbb_quali_active"))


def is_fmbb_entry(entry: dict) -> bool:
    """
    True wenn die Anmeldung als FMBB-Teilnehmer markiert ist.
    Reine Flag-Prüfung — kein heuristischer Rasse-Filter (User-Entscheid 2026-06-14).
    """
    return bool(entry.get("is_fmbb"))


def mark_fmbb_by_licenses(event: dict, licenses: list[str] | set[str],
                          reset: bool = True) -> dict:
    """
    Bulk-Setzen des `is_fmbb`-Flags über eine Liste von Lizenznummern.

    Wenn `reset=True` (Default): alle Anmeldungen werden zuerst auf
    `is_fmbb=False` gesetzt, dann die in `licenses` enthaltenen auf True.
    Wenn `reset=False`: nur die in `licenses` enthaltenen werden auf True
    gesetzt, andere bleiben unverändert.

    Lizenzen werden case-insensitive verglichen, mit Whitespace-Trim.

    Returns: dict mit Statistik
      {
        "matched":   int,  # Anzahl Anmeldungen mit is_fmbb=True nach Lauf
        "unmatched": list, # Lizenzen aus der Eingabeliste die im Event nicht vorkommen
        "total_entries": int,
      }
    """
    license_set = {str(lic).strip().upper() for lic in licenses if str(lic).strip()}
    found_licenses: set[str] = set()
    matched = 0
    total = 0

    for run in event.get("runs", []):
        for entry in run.get("entries", []):
            total += 1
            entry_lic = (entry.get("Lizenznummer") or "").strip().upper()
            if entry_lic and entry_lic in license_set:
                entry["is_fmbb"] = True
                matched += 1
                found_licenses.add(entry_lic)
            elif reset:
                entry["is_fmbb"] = False

    unmatched = sorted(license_set - found_licenses)
    return {
        "matched":       matched,
        "unmatched":     unmatched,
        "total_entries": total,
    }


# ---------------------------------------------------------------------------
# Public API — Tag-Auswertung
# ---------------------------------------------------------------------------

def calculate_fmbb_quali(event: dict) -> dict:
    """
    Tag-Auswertung für ein FMBB-Quali-Event.

    Geht alle Läufe des Events durch und liefert pro relevantem Lauf
    (Kategorie egal, Klasse ∈ FMBB_ELIGIBLE_CLASSES, Laufart Agi/Jump)
    die gefilterte Rangliste der FMBB-markierten Teilnehmer.

    Returns: dict mit Struktur
      {
        "active":   bool,
        "runs":     [
          {
            "kategorie", "klasse", "laufart",
            "rankings": [...],
          },
          ...
        ],
        "total_fmbb_teams": int,   # unique Lizenzen unter den markierten Teilnehmern
      }
    """
    result_runs: list[dict] = []
    fmbb_licenses: set[str] = set()

    for run in event.get("runs", []):
        klasse  = str(run.get("klasse") or "")
        laufart = run.get("laufart") or ""
        if klasse not in FMBB_ELIGIBLE_CLASSES or laufart not in FMBB_RUN_TYPES:
            continue

        fmbb_entries = [e for e in (run.get("entries") or []) if is_fmbb_entry(e)]
        if not fmbb_entries:
            continue

        normalised = [_normalise_entry(e) for e in fmbb_entries if (e.get("Lizenznummer") or "").strip()]
        rankings = _sort_fmbb_ranking(normalised)

        for r in normalised:
            if r["license"]:
                fmbb_licenses.add(r["license"])

        result_runs.append({
            "kategorie": run.get("kategorie") or "",
            "klasse":    klasse,
            "laufart":   laufart,
            "rankings":  rankings,
        })

    return {
        "active":            is_fmbb_active(event),
        "runs":              result_runs,
        "total_fmbb_teams":  len(fmbb_licenses),
    }


# ---------------------------------------------------------------------------
# Helpers (intern)
# ---------------------------------------------------------------------------

DIS_SENTINEL_FEHLER = 999.0


def _normalise_entry(entry: dict) -> dict:
    """Wandelt ein AgilitySoftware-entry in eine normalisierte FMBB-Form."""
    license_no = (entry.get("Lizenznummer") or "").strip()
    dis_val = entry.get("disqualifikation") or ""
    fehler_total = entry.get("fehler_total", DIS_SENTINEL_FEHLER)
    is_dis = (
        dis_val in ("DIS", "ABR", "DNS")
        or float(fehler_total) >= DIS_SENTINEL_FEHLER
    )
    return {
        "license":         license_no,
        "dog_name":        entry.get("Hundename") or entry.get("dog_name") or "",
        "handler_name":    (
            (entry.get("Vorname", "") + " " + entry.get("Nachname", "")).strip()
            or entry.get("handler_name") or ""
        ),
        "fehler_total":    float(fehler_total) if not is_dis else DIS_SENTINEL_FEHLER,
        "fehler_parcours": int(entry.get("fehler_parcours", 0) or 0),
        "zeit":            float(entry.get("zeit_total", 999.99)) if not is_dis else 999.99,
        "rang":            entry.get("platz"),
        "dis":             is_dis,
    }


def _sort_fmbb_ranking(entries: list) -> list:
    """
    Sortierung: nicht-DIS zuerst (sortiert nach rang),
    DIS-Teams am Ende (in Eingabe-Reihenfolge).
    Nutzt `rang` von AgilitySoftware — keine eigene Tiebreaker-Logik
    (User-Entscheid: keine Punkteformel im Tool).
    """
    platzierte = sorted(
        [e for e in entries if not e["dis"] and e["rang"] is not None],
        key=lambda e: e["rang"],
    )
    dis = [e for e in entries if e["dis"]]
    return platzierte + dis
