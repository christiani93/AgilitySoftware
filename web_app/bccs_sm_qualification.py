"""
BCCS-Schweizermeisterschaft Agility – Qualifikationsberechnung
==============================================================

Reglement: "Border Collie Club Schweiz – Reglement für die Agility
Schweizermeisterschaft", genehmigt 30.11.2022 (PDF 2023). Eigenständige
Veranstaltungsart, NICHT zu verwechseln mit SKBS-SM (skbs_sm_qualification.py)
oder TKAMO-SM (sm_qualification.py) — andere Quote, andere Kategorien,
anderer Final-Modus.

Spezifika BCCS-SM (Reglement Punkt 2–4):
- Nur Border Collies, Kategorien **Intermediate (I) + Large (L)**.
- Zwei parallele Bewerbe ("Divisionen"):
    * **SM**        = Klasse 3        → Titel "… Agility Schweizermeister BCCS"
    * **Nachwuchs** = Klassen 1 + 2   → Titel "… Nachwuchs Agility Schweizermeister BCCS"
  → also 4 Endläufe: (I, L) × (SM, Nachwuchs).
- Pro Division: 2 Qualifikationsläufe (1 Agility + 1 Jumping), identische Startreihenfolge.
- Pro Qualilauf qualifizieren sich die **ersten 15 %** der gestarteten SM-Hunde
  (aufgerundet) für den Final.
- Doppelqualifikation → **Nachrücken**: nach Abschluss beider Quali rückt
  abwechselnd das nächstplatzierte, noch nicht qualifizierte Team nach —
  zuerst aus dem 1. Qualilauf, dann aus dem 2., usw., bis die Maximalzahl
  (= Summe der beiden Quoten) erreicht ist. **Kein Fehlerpunkte-Deckel**
  (anders als SKBS Art. 22b).
- **Titelverteidiger** (amtierender SM der Division) gesetzt, sofern in ≥1
  Qualilauf gestartet. Qualifiziert er sich via Quali, rückt ein anderes Team nach.

Final (Reglement 3.2): **2 Finalläufe** (zuerst Jumping, dann Agility), Rangierung
durch Addition beider Läufe. 3-stufiger Tiebreaker + ex aequo:
  1. kleinere Summe Gesamtfehlerpunkte (Parcours- + Zeitfehler)
  2. kleinere Summe Parcoursfehler
  3. kleinere Summe Laufzeiten

OFFENE ANNAHMEN (vor produktivem Einsatz mit User verifizieren!):
- **Nachwuchs-Kombination**: Klassen 1 + 2 werden hier zu EINEM Pool je Laufart
  zusammengefasst und rein nach Leistung (Fehler→Parcours→Zeit) gerankt (für den
  15 %-Cutoff). Ob das Reglement Kl.1/Kl.2 wirklich kombiniert oder getrennt
  wertet, ist nicht 100 % eindeutig — annehmen & bestätigen lassen.
- **Quali-Lauf-Reihenfolge** (für die Nachrück-Alternierung): Reihenfolge ist
  Veranstaltersache. Default hier ["Agility", "Jumping"]; überschreibbar via
  event["bccs_sm_config"]["quali_run_order"].
- **Keine Mindest-Quote**: reines ceil(15 %). Reglement nennt keinen Minimalwert
  (anders als SKBS min. 3).

Datenformat-Erwartungen am `event`-Dict (identisch zu skbs_sm_qualification.py):
  event["runs"]: Liste von Lauf-Dicts mit Feldern:
    - kategorie:  "Intermediate" | "Large"
    - klasse:     "1" | "2" | "3"
    - laufart:    "Agility" | "Jumping"
    - is_final:   True für die beiden Finalläufe
    - entries:    Liste von Teilnehmer-Dicts (Lizenznummer, fehler_total, ...)
  event["bccs_sm_config"]:
    - quali_run_order:    ["Agility", "Jumping"] | ["Jumping", "Agility"]
    - defending_champions: [ {"license", "dog_name", "handler_name",
                              "category": "Intermediate"|"Large",
                              "division": "sm"|"nachwuchs"}, ... ]
"""
from __future__ import annotations

import math


CATEGORIES = ["Intermediate", "Large"]
DIVISIONS = {
    "sm":        {"label": "SM",        "classes": ["3"]},
    "nachwuchs": {"label": "Nachwuchs", "classes": ["1", "2"]},
}
QUALI_RUN_TYPES = ["Agility", "Jumping"]
QUOTA_PCT = 0.15                                # Reglement 3.1: 15 %
DIS_SENTINEL_FEHLER = 999.0                     # passend zu sm_qualification.py-Konvention
DIS_SENTINEL_ZEIT = 999.99


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_bccs_sm_qualification(event: dict) -> dict:
    """
    Berechnet die BCCS-SM-Qualifikation für ein Event über alle 4 Divisionen
    (Intermediate/Large × SM/Nachwuchs).

    Returns: dict mit Struktur:
      {
        "divisions": {
          "Intermediate/sm":        {division-result}, ...
          "Large/nachwuchs":        {division-result},
        },
        "finalists": [ {license, dog_name, handler_name, source, category,
                        division, from_class, quali_rank}, ... ],   # flach, alle Divisionen
      }
    division-result:
      {"category", "division", "quota": {"Agility": int, "Jumping": int},
       "finalists": [...], "open_spots": int}
    """
    config = event.get("bccs_sm_config") or {}
    quali_order = _resolve_quali_order(config.get("quali_run_order"))
    defenders = config.get("defending_champions") or []

    divisions: dict[str, dict] = {}
    all_finalists: list[dict] = []

    for category in CATEGORIES:
        for div_key, div_def in DIVISIONS.items():
            quali_pools, _final_pools = _collect_division(event, category, div_def["classes"])
            defending = _find_defender(defenders, category, div_key)
            res = _compute_division(quali_pools, quali_order, defending)
            res["category"] = category
            res["division"] = div_key
            for f in res["finalists"]:
                f["category"] = category
                f["division"] = div_key
                all_finalists.append(f)
            divisions[f"{category}/{div_key}"] = res

    return {"divisions": divisions, "finalists": all_finalists}


def rank_final_bccs(event: dict) -> dict:
    """
    Berechnet die Final-Rangierung je Division aus den 2 Finalläufen (Jumping + Agility),
    summiert mit 3-stufigem Tiebreaker + ex aequo.

    Returns: dict  "Category/division" → Liste von Result-Dicts mit `final_rang`.
    """
    out: dict[str, list[dict]] = {}
    for category in CATEGORIES:
        for div_key, div_def in DIVISIONS.items():
            _quali_pools, final_pools = _collect_division(event, category, div_def["classes"])
            out[f"{category}/{div_key}"] = _rank_division_final(final_pools)
    return out


# ---------------------------------------------------------------------------
# Internal helpers — Sammeln / Normalisieren
# ---------------------------------------------------------------------------

def _resolve_quali_order(order) -> list[str]:
    """Validiert die Quali-Lauf-Reihenfolge; Fallback ["Agility", "Jumping"]."""
    if isinstance(order, (list, tuple)) and set(order) == set(QUALI_RUN_TYPES):
        return list(order)
    return list(QUALI_RUN_TYPES)


def _find_defender(defenders: list[dict], category: str, div_key: str):
    """Sucht den Titelverteidiger für eine bestimmte Division."""
    for d in defenders:
        if (d.get("category") == category and d.get("division") == div_key
                and (d.get("license") or "").strip()):
            return d
    return None


def _collect_division(event: dict, category: str, division_classes: list[str]):
    """
    Sammelt Quali- und Final-Einträge einer Division (Kategorie + Klassen-Gruppe).

    Returns: (quali_pools, final_pools), je dict laufart → Liste normalisierter Einträge.
    Für Nachwuchs (Klassen 1+2) werden die Einträge je Laufart über die Klassen
    hinweg zu EINEM Pool zusammengefasst.
    """
    quali = {"Agility": [], "Jumping": []}
    final = {"Agility": [], "Jumping": []}

    for run in event.get("runs", []):
        if run.get("kategorie") != category:
            continue
        cls = str(run.get("klasse") or "")
        if cls not in division_classes:
            continue
        laufart = run.get("laufart") or ""
        if laufart not in QUALI_RUN_TYPES:
            continue
        bucket = final if run.get("is_final") else quali
        for e in run.get("entries", []):
            if not (e.get("Lizenznummer") or "").strip():
                continue
            ne = _normalise_entry(e)
            ne["from_class"] = int(cls) if cls.isdigit() else None
            bucket[laufart].append(ne)

    return quali, final


def _normalise_entry(entry: dict) -> dict:
    """Wandelt ein AgilitySoftware-entry in eine normalisierte Result-Repräsentation."""
    license_no = (entry.get("Lizenznummer") or "").strip()
    dis_val = (entry.get("disqualifikation") or "").strip()
    fehler_total = entry.get("fehler_total", DIS_SENTINEL_FEHLER)
    is_dns = dis_val == "DNS"
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
        "zeit":            float(entry.get("zeit_total", DIS_SENTINEL_ZEIT)) if not is_dis else DIS_SENTINEL_ZEIT,
        "rang":            entry.get("platz"),
        "dis":             is_dis,
        "dns":             is_dns,
    }


def _quota(num_starters: int) -> int:
    """Reglement 3.1: erste 15 % der gestarteten SM-Hunde, aufgerundet. Kein Minimum."""
    if num_starters <= 0:
        return 0
    return math.ceil(num_starters * QUOTA_PCT)


def _performance_sorted(entries: list[dict]) -> list[dict]:
    """
    Nur platzierte (nicht-DIS) Einträge, gerankt nach Leistung:
    Gesamtfehler → Parcoursfehler → Zeit. Ermöglicht die klassenübergreifende
    Reihung der Nachwuchs-Division (Kl.1+2) wie auch die SM-Division (Kl.3).
    """
    valid = [e for e in entries if not e["dis"]]
    return sorted(valid, key=lambda e: (e["fehler_total"], e["fehler_parcours"], e["zeit"]))


def _count_starters(pool: list[dict]) -> int:
    """Gestartete Teams = alle ausser DNS. DIS/ABR zählen als gestartet."""
    starters = sum(1 for e in pool if not e["dns"])
    return starters if starters > 0 else len(pool)


# ---------------------------------------------------------------------------
# Internal — Qualifikation pro Division
# ---------------------------------------------------------------------------

def _compute_division(quali_pools: dict, quali_order: list[str], defending) -> dict:
    """
    Qualifikation einer einzelnen Division (z.B. Large/SM):
    15 %-Direktquote pro Lauf, Doppelqualifikation überspringen, alternierendes
    Nachrücken zwischen den beiden Quali-Läufen bis zur Maximalzahl.
    """
    qualified: set[str] = set()
    finalists: list[dict] = []

    # Titelverteidiger zuerst (zählt extra, nimmt keinen Direktslot weg)
    if defending and defending.get("license"):
        lic = defending["license"].strip()
        started = any(
            any(e["license"] == lic for e in quali_pools.get(la, []))
            for la in QUALI_RUN_TYPES
        )
        if started and lic not in qualified:
            finalists.append({
                "license":      lic,
                "dog_name":     defending.get("dog_name", ""),
                "handler_name": defending.get("handler_name", ""),
                "source":       "title_defender",
                "from_class":   None,
                "quali_rank":   None,
            })
            qualified.add(lic)

    # Direkt-Qualifikation pro Lauf (in konfigurierter Reihenfolge)
    run_quota: dict[str, int] = {}
    run_sorted: dict[str, list[dict]] = {}
    for la in quali_order:
        pool = quali_pools.get(la, [])
        quota = _quota(_count_starters(pool))
        placed = _performance_sorted(pool)
        run_quota[la] = quota
        run_sorted[la] = placed

        given = 0
        for idx, e in enumerate(placed):
            if given >= quota:
                break
            if e["license"] in qualified:
                given += 1   # Doppelqualifikation → Lücke, später per Nachrücken gefüllt
                continue
            qualified.add(e["license"])
            finalists.append({
                "license":      e["license"],
                "dog_name":     e["dog_name"],
                "handler_name": e["handler_name"],
                "source":       la.lower(),       # "agility" | "jumping"
                "from_class":   e["from_class"],
                "quali_rank":   idx + 1,
            })
            given += 1

    # Maximalzahl = Summe der Quoten; offene Plätze per Nachrücken alternierend füllen
    target = sum(run_quota.values())
    direct = sum(1 for f in finalists if f["source"] != "title_defender")
    remaining = max(0, target - direct)

    if remaining > 0:
        pointers = {la: 0 for la in quali_order}
        exhausted = {la: False for la in quali_order}
        while remaining > 0 and not all(exhausted.values()):
            progressed = False
            for la in quali_order:
                if remaining <= 0:
                    break
                placed = run_sorted[la]
                p = pointers[la]
                while p < len(placed) and placed[p]["license"] in qualified:
                    p += 1
                pointers[la] = p
                if p >= len(placed):
                    exhausted[la] = True
                    continue
                e = placed[p]
                qualified.add(e["license"])
                pointers[la] = p + 1
                progressed = True
                finalists.append({
                    "license":      e["license"],
                    "dog_name":     e["dog_name"],
                    "handler_name": e["handler_name"],
                    "source":       "nachruecker",
                    "from_class":   e["from_class"],
                    "quali_rank":   p + 1,
                })
                remaining -= 1
            if not progressed:
                break

    return {
        "quota":      dict(run_quota),
        "finalists":  finalists,
        "open_spots": remaining,
    }


# ---------------------------------------------------------------------------
# Internal — Final-Rangierung (2 Läufe summiert)
# ---------------------------------------------------------------------------

def _rank_division_final(final_pools: dict) -> list[dict]:
    """
    Rangiert eine Division aus den 2 Finalläufen (Summe Jumping + Agility).
    Teams ohne beide Läufe oder mit DIS in einem Lauf werden ohne Rang ans Ende gesetzt.
    """
    by_lic: dict[str, dict] = {}
    for la in QUALI_RUN_TYPES:
        for e in final_pools.get(la, []):
            d = by_lic.setdefault(e["license"], {
                "license":      e["license"],
                "dog_name":     e["dog_name"],
                "handler_name": e["handler_name"],
                "runs":         {},
            })
            d["runs"][la] = e

    results: list[dict] = []
    for d in by_lic.values():
        runs = d["runs"]
        has_both = all(la in runs for la in QUALI_RUN_TYPES)
        any_dis = any(r["dis"] for r in runs.values())
        if not has_both or any_dis:
            d["dis"] = True
            d["sum_fehler"] = d["sum_parcours"] = d["sum_zeit"] = None
        else:
            d["dis"] = False
            d["sum_fehler"]   = round(sum(r["fehler_total"] for r in runs.values()), 3)
            d["sum_parcours"] = sum(r["fehler_parcours"] for r in runs.values())
            d["sum_zeit"]     = round(sum(r["zeit"] for r in runs.values()), 3)
        results.append(d)

    valid = [d for d in results if not d["dis"]]
    valid.sort(key=lambda d: (d["sum_fehler"], d["sum_parcours"], d["sum_zeit"]))

    out: list[dict] = []
    rank = 0
    last_key = None
    for i, d in enumerate(valid, start=1):
        key = (d["sum_fehler"], d["sum_parcours"], d["sum_zeit"])
        if key != last_key:
            rank = i
            last_key = key
        d["final_rang"] = rank
        out.append(d)

    for d in results:
        if d["dis"]:
            d["final_rang"] = None
            out.append(d)

    return out
