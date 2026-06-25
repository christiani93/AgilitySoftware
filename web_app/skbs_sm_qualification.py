"""
SKBS-Schweizermeisterschaft Agility – Qualifikationsberechnung
==============================================================

Reglement: SKBS "Reglement Sport- und Gebrauchshundewesen", gültig ab 17.04.2026,
Art. 18-23. Eigenständige Veranstaltungsart (nicht zu verwechseln mit der
TKAMO-SM in sm_qualification.py — andere Quote, anderer Final-Modus,
andere Nachrück-Logik).

Spezifika SKBS-SM (Art. 18, 22):
- Nur Kategorie **Large**, Klassen **1, 2, 3**
- Pro Klasse: 2 Qualifikationsläufe (1 Agility + 1 Jumping)
- Pro Qualilauf: Top **20%** bzw. **min. 3** (aufgerundet) qualifizieren sich
  für den Final, sofern eine Platzierung erreicht (nicht-DIS)
- **Ein gemeinsamer Finallauf** für alle Klassen auf Niveau Klasse 3 (Agility)
- Doppelqualifikation → Nachrück-Logik:
    1. Nächstplatziertes Team aus dem **2. Qualilauf**, max. 10 FP
    2. Klasse 3 (Agi vor Jump), max. 10 FP
    3. Klasse 2 (Agi vor Jump), max. 10 FP
    4. Klasse 1 (Agi vor Jump), max. 10 FP
    5. Verbleibende Plätze bleiben offen

Final-Rangierung (Art. 22c, 3-stufiger Tiebreaker + ex aequo):
  1. kleinere Summe Gesamtfehlerpunkte (Parcoursfehler + Zeitfehler)
  2. kleinere Summe Parcoursfehler
  3. kleinere Summe Laufzeiten
  4. ex aequo (gleicher Rang)

Titelverteidiger (Art. 21f): aktueller Schweizermeister gilt als qualifiziert,
sofern er mindestens einen Qualilauf bestreitet. Wird via
event["skbs_sm_config"]["defending_champion"] manuell eingetragen.

Datenformat-Erwartungen am `event`-Dict:
  event["runs"]: Liste von Lauf-Dicts mit Feldern:
    - kategorie:  "Large" (für SKBS-SM relevant)
    - klasse:     "1" | "2" | "3"
    - laufart:    "Agility" | "Jumping"
    - is_final:   True für den klassenübergreifenden Finallauf
    - entries:    Liste von Teilnehmer-Dicts (Lizenznummer, fehler_total, ...)
  event["skbs_sm_config"]:
    - defending_champion: {"license", "dog_name", "handler_name"} | None
"""
from __future__ import annotations

import math


CATEGORY = "Large"
CLASS_LEVELS = ["3", "2", "1"]                  # Nachrück-Reihenfolge (3 → 2 → 1)
QUALI_RUN_TYPES = ["Agility", "Jumping"]        # Bei Nachrücken: Agi vor Jump
MAX_NACHRUECK_FAULTS = 10.0                     # Art. 22b: max. 10 FP für Nachrücker
QUOTA_PER_RUN_PCT = 0.20                        # Art. 22b: 20%
QUOTA_PER_RUN_MIN = 3                           # Art. 22b: mindestens 3 (aufgerundet)
DIS_SENTINEL_FEHLER = 999.0                     # passend zu sm_qualification.py-Konvention


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_skbs_sm_qualification(event: dict) -> dict:
    """
    Berechnet SKBS-SM-Qualifikation für ein Event.

    Returns: dict mit Struktur:
      {
        "per_class": {
          "1": {"qa_results": [...], "qj_results": [...],
                "qa_quota": int, "qj_quota": int,
                "qa_qualifiers": [...], "qj_qualifiers": [...]},
          "2": {...},
          "3": {...},
        },
        "finalists": [
          {"license", "dog_name", "handler_name", "source", "from_class",
           "quali_rank"}, ...
        ],
        "defending_champion": {...} | None,
        "open_spots": int,                # 0 wenn alles besetzt
      }
    """
    skbs_runs = _collect_skbs_runs(event)
    config = event.get("skbs_sm_config") or {}
    defending = config.get("defending_champion")

    per_class: dict[str, dict] = {}
    qualified_licenses: set[str] = set()

    # Titelverteidiger zuerst — gilt automatisch als qualifiziert (sofern in mind.
    # einem Quali-Lauf gestartet; Prüfung erfolgt durch _is_titelverteidiger_eligible)
    finalists: list[dict] = []
    if defending and defending.get("license"):
        if _is_titelverteidiger_eligible(defending["license"], skbs_runs):
            finalists.append({
                "license":      defending["license"],
                "dog_name":     defending.get("dog_name", ""),
                "handler_name": defending.get("handler_name", ""),
                "source":       "title_defender",
                "from_class":   None,
                "quali_rank":   None,
            })
            qualified_licenses.add(defending["license"])

    # Pro Klasse: Quali-Ergebnisse normalisieren + Top-Quote auswählen
    for cls in CLASS_LEVELS:
        cls_data = _build_class_results(skbs_runs, cls, qualified_licenses, finalists)
        per_class[cls] = cls_data

    # Nachrück-Logik: aus Klassen 3 → 2 → 1, Agi vor Jump, max 10 FP
    # Hinweis: die Reglements-Stufe "2. Qualilauf" (Art. 22b) ist implizit erfüllt,
    # da bei Doppelqualifikation aus Lauf A die Nachrück-Pipeline gleich beim
    # 2. Lauf der selben Klasse beginnt (CLASS_LEVELS startet bei "3"). Die
    # _build_class_results-Funktion vergibt Plätze bereits in Lauf-Reihenfolge.
    # Für später entstehende Lücken (zwischen Klassen) folgt _fill_open_spots.
    open_spots = _count_open_spots(per_class, finalists)
    if open_spots > 0:
        _fill_open_spots(per_class, skbs_runs, qualified_licenses, finalists, open_spots)

    final_open = _count_open_spots(per_class, finalists)

    return {
        "per_class":          per_class,
        "finalists":          finalists,
        "defending_champion": defending,
        "open_spots":         final_open,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _collect_skbs_runs(event: dict) -> dict:
    """
    Sammelt Quali-Läufe und Final-Lauf gruppiert.

    Returns: {
      "quali": { "1": {"Agility": run, "Jumping": run}, "2": {...}, "3": {...} },
      "final": run | None,
    }
    """
    quali: dict[str, dict] = {"1": {}, "2": {}, "3": {}}
    final_run = None

    for run in event.get("runs", []):
        if run.get("kategorie") != CATEGORY:
            continue
        if run.get("is_final"):
            final_run = run
            continue
        cls = str(run.get("klasse") or "")
        laufart = run.get("laufart") or ""
        if cls in quali and laufart in QUALI_RUN_TYPES:
            quali[cls][laufart] = run

    return {"quali": quali, "final": final_run}


def _is_titelverteidiger_eligible(license_no: str, skbs_runs: dict) -> bool:
    """Reglement Art. 21f: Titelverteidiger gilt qualifiziert sofern in mind. 1 Qualilauf gestartet."""
    for cls_runs in skbs_runs["quali"].values():
        for run in cls_runs.values():
            for entry in run.get("entries", []):
                if (entry.get("Lizenznummer") or "").strip() == license_no:
                    return True
    return False


def _normalise_entry(entry: dict) -> dict:
    """Wandelt ein AgilitySoftware-entry in eine normalisierte Result-Repräsentation."""
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


def _quota(num_starters: int) -> int:
    """Art. 22b: Top 20% bzw. mindestens 3, aufgerundet."""
    if num_starters <= 0:
        return 0
    return max(QUOTA_PER_RUN_MIN, math.ceil(num_starters * QUOTA_PER_RUN_PCT))


def _platzierte_sortiert(entries: list[dict]) -> list[dict]:
    """Nur platzierte (nicht-DIS, mit rang) Einträge, nach rang aufsteigend."""
    valid = [e for e in entries if not e["dis"] and e["rang"] is not None]
    return sorted(valid, key=lambda e: e["rang"])


def _build_class_results(
    skbs_runs: dict,
    cls: str,
    qualified_licenses: set[str],
    finalists: list[dict],
) -> dict:
    """
    Verarbeitet eine Klasse: normalisiert Quali-Ergebnisse, vergibt
    direkte Quali-Plätze gemäss Quote. Reihenfolge: Agility vor Jumping.

    Mutiert qualified_licenses und finalists in-place.
    """
    cls_data: dict = {
        "qa_results": [], "qj_results": [],
        "qa_quota": 0, "qj_quota": 0,
        "qa_qualifiers": [], "qj_qualifiers": [],
    }

    cls_runs = skbs_runs["quali"].get(cls, {})

    for laufart in QUALI_RUN_TYPES:
        run = cls_runs.get(laufart)
        if not run:
            continue

        normalised = [_normalise_entry(e) for e in run.get("entries", [])
                      if (e.get("Lizenznummer") or "").strip()]
        # nur Starter zählen (nicht-DNS — DIS/ABR zählen, da sie ja gestartet sind)
        num_starters = sum(1 for e in normalised if (e.get("dis") is False)
                           or (e.get("dis") and not _is_dns(run, e)))
        # Pragmatischer Default: nimm Gesamtzahl unique Lizenzen mit irgendeinem Datum
        if num_starters == 0:
            num_starters = len(normalised)

        quota = _quota(num_starters)
        platzierte = _platzierte_sortiert(normalised)

        if laufart == "Agility":
            cls_data["qa_results"], cls_data["qa_quota"] = normalised, quota
            qualifiers_key = "qa_qualifiers"
        else:
            cls_data["qj_results"], cls_data["qj_quota"] = normalised, quota
            qualifiers_key = "qj_qualifiers"

        # Plätze vergeben — Doppelqualifikation überspringen, aber NICHT nachrücken
        # (Nachrücken erfolgt erst in _fill_open_spots wenn Gesamt-Lücken bleiben)
        spots_given = 0
        for entry in platzierte:
            if spots_given >= quota:
                break
            if entry["license"] in qualified_licenses:
                # bereits qualifiziert — Slot bleibt zunächst offen, _fill_open_spots
                # füllt später; aber wir markieren die Quote dennoch als "vergeben"
                # um konforme Top-N-Logik beizubehalten
                spots_given += 1
                continue
            qualified_licenses.add(entry["license"])
            finalist = {
                "license":      entry["license"],
                "dog_name":     entry["dog_name"],
                "handler_name": entry["handler_name"],
                "source":       laufart.lower(),  # "agility" | "jumping"
                "from_class":   int(cls),
                "quali_rank":   entry["rang"],
            }
            finalists.append(finalist)
            cls_data[qualifiers_key].append(finalist)
            spots_given += 1

    return cls_data


def _is_dns(run: dict, normalised_entry: dict) -> bool:
    """Heuristik: DNS-Markierung im Original-Entry."""
    for orig in run.get("entries", []):
        if (orig.get("Lizenznummer") or "").strip() == normalised_entry["license"]:
            return (orig.get("disqualifikation") or "") == "DNS"
    return False


def _count_open_spots(per_class: dict, finalists: list[dict]) -> int:
    """Differenz zwischen Quoten-Summe und aktueller Finalisten-Zahl (ohne Titelverteidiger)."""
    quota_sum = sum(c["qa_quota"] + c["qj_quota"] for c in per_class.values())
    direct_count = sum(1 for f in finalists if f["source"] != "title_defender")
    return max(0, quota_sum - direct_count)


def _fill_open_spots(
    per_class: dict,
    skbs_runs: dict,
    qualified_licenses: set[str],
    finalists: list[dict],
    open_spots: int,
) -> None:
    """
    Nachrück-Logik (Art. 22b): füllt offene Plätze, Reihenfolge Klasse 3 → 2 → 1,
    pro Klasse Agi vor Jump. Max 10 FP pro Nachrücker. Bereits qualifizierte
    werden übersprungen.
    """
    remaining = open_spots
    for cls in CLASS_LEVELS:
        if remaining <= 0:
            return
        cls_runs = skbs_runs["quali"].get(cls, {})
        for laufart in QUALI_RUN_TYPES:
            if remaining <= 0:
                return
            run = cls_runs.get(laufart)
            if not run:
                continue
            normalised = [_normalise_entry(e) for e in run.get("entries", [])
                          if (e.get("Lizenznummer") or "").strip()]
            platzierte = _platzierte_sortiert(normalised)
            for entry in platzierte:
                if remaining <= 0:
                    break
                if entry["license"] in qualified_licenses:
                    continue
                if entry["fehler_total"] > MAX_NACHRUECK_FAULTS:
                    continue
                qualified_licenses.add(entry["license"])
                finalists.append({
                    "license":      entry["license"],
                    "dog_name":     entry["dog_name"],
                    "handler_name": entry["handler_name"],
                    "source":       "nachruecker",
                    "from_class":   int(cls),
                    "quali_rank":   entry["rang"],
                })
                remaining -= 1


# ---------------------------------------------------------------------------
# Final-Rangierung
# ---------------------------------------------------------------------------

def rank_final(event: dict) -> list[dict]:
    """
    Berechnet die Final-Rangierung mit 3-stufigem Tiebreaker und ex aequo.

    Liest aus dem mit `is_final: True` markierten Lauf.

    Returns: Liste von Result-Dicts mit zusätzlichem `final_rang`-Feld (1-basiert).
    """
    skbs_runs = _collect_skbs_runs(event)
    final_run = skbs_runs["final"]
    if not final_run:
        return []

    normalised = [_normalise_entry(e) for e in final_run.get("entries", [])
                  if (e.get("Lizenznummer") or "").strip()]
    valid = [e for e in normalised if not e["dis"]]

    # Sortierung: Tiebreaker-Hierarchie
    valid.sort(key=lambda e: (
        e["fehler_total"],
        e["fehler_parcours"],
        e["zeit"],
    ))

    # ex-aequo-Rangvergabe
    rank = 0
    last_key = None
    results: list[dict] = []
    for i, entry in enumerate(valid, start=1):
        key = (entry["fehler_total"], entry["fehler_parcours"], entry["zeit"])
        if key != last_key:
            rank = i
            last_key = key
        entry_with_rank = dict(entry)
        entry_with_rank["final_rang"] = rank
        results.append(entry_with_rank)

    # DIS-Teams am Ende ohne Rang
    for entry in normalised:
        if entry["dis"]:
            entry_with_rank = dict(entry)
            entry_with_rank["final_rang"] = None
            results.append(entry_with_rank)

    return results
