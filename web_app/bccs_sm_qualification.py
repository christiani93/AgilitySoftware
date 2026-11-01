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

GEKLÄRT (User-Klarstellung 2026-06-25):
- **Nachwuchs Kl.1 und Kl.2 werden SEPARAT gewertet** in den Qualiläufen → die 15 %-Quote
  gilt **pro (Kategorie × Klasse)** (I-Kl1, I-Kl2, L-Kl1, L-Kl2 je eigene Quali). NICHT kombiniert.
  Der gemeinsame Final je Kategorie kombiniert Kl.1+2 (siehe rank_final_bccs).
- **Quali-Lauf-Reihenfolge** (Nachrück-Alternierung) = tatsächliche Reihenfolge an der
  Veranstaltung (Veranstaltersache); via event["bccs_sm_config"]["quali_run_order"],
  Default ["Agility", "Jumping"].
- **Keine Mindest-Quote**: reines ceil(15 %) (anders als SKBS min. 3).

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

import copy
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

def calculate_bccs_sm_qualification(event: dict, recalc_fn=None) -> dict:
    """
    Berechnet die BCCS-SM-Qualifikation für ein Event über alle 4 Divisionen
    (Intermediate/Large × SM/Nachwuchs).

    `recalc_fn` (optional): Callable `fn(run_dict) -> Any`, das die Ergebnisfelder
    (fehler_total/zeit_total/fehler_parcours/platz/…) der Entries eines Laufs
    IN PLACE neu berechnet — über genau das Feld, das in `run_dict["entries"]`
    steckt. Wird gebraucht, weil die SCT in Kl.2/3 dynamisch aus der schnellsten
    berücksichtigten Zeit abgeleitet wird: Die BCCS-only-Rangliste muss ihre
    Zeitfehler aus dem SM-Feld neu rechnen, sonst stammen sie aus der offenen
    (Gesamtfeld-)Berechnung und sind falsch. Ohne `recalc_fn` (bzw. ohne SM-Filter
    oder ohne Rohdaten) gilt der abwärtskompatible Fallback auf die gespeicherten
    Werte. Siehe `_sm_entries_for_run`.

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
    sm_filter = _build_sm_predicate(event)

    divisions: dict[str, dict] = {}
    all_finalists: list[dict] = []

    for category in CATEGORIES:
        for div_key, div_def in DIVISIONS.items():
            qualified: set[str] = set()
            div_finalists: list[dict] = []

            # Titelverteidiger division-weit (gesetzt, wenn in >=1 Quali-Lauf der Division gestartet)
            defending = _find_defender(defenders, category, div_key)
            if defending and (defending.get("license") or "").strip():
                lic = defending["license"].strip()
                if _defender_started(event, category, div_def["classes"], lic):
                    div_finalists.append({
                        "license": lic,
                        "dog_name": defending.get("dog_name", ""),
                        "handler_name": defending.get("handler_name", ""),
                        "source": "title_defender", "from_class": None, "quali_rank": None,
                    })
                    qualified.add(lic)

            # Klassen der Division SEPARAT werten (Kl.1/Kl.2 getrennt; 15 % je Klasse)
            quota: dict[str, int] = {}
            open_spots = 0
            for cls in div_def["classes"]:
                res = _compute_class(_collect_class(event, category, cls, sm_filter, recalc_fn), quali_order, qualified)
                div_finalists.extend(res["finalists"])
                for la, q in res["quota"].items():
                    quota[la] = quota.get(la, 0) + q
                open_spots += res["open_spots"]

            for f in div_finalists:
                f["category"] = category
                f["division"] = div_key
                all_finalists.append(f)
            divisions[f"{category}/{div_key}"] = {
                "category": category, "division": div_key,
                "quota": quota, "finalists": div_finalists, "open_spots": open_spots,
            }

    return {"divisions": divisions, "finalists": all_finalists}


def rank_final_bccs(event: dict, recalc_fn=None) -> dict:
    """
    Berechnet die Final-Rangierung je Division aus den 2 Finalläufen (Jumping + Agility),
    summiert mit 3-stufigem Tiebreaker + ex aequo.

    `recalc_fn`: s. calculate_bccs_sm_qualification (SCT-Neuberechnung über SM-Feld).

    Returns: dict  "Category/division" → Liste von Result-Dicts mit `final_rang`.
    """
    sm_filter = _build_sm_predicate(event)
    out: dict[str, list[dict]] = {}
    for category in CATEGORIES:
        for div_key, div_def in DIVISIONS.items():
            _quali_pools, final_pools = _collect_division(event, category, div_def["classes"], sm_filter, recalc_fn)
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


def _build_sm_predicate(event: dict):
    """
    Baut das SM-Hund-Filterprädikat (Reglement P.2): Das BCCS-SM läuft als normales
    offenes Turnier; nur **SM-Hunde** (Border Collie, die an der SM teilnehmen) zählen
    für die 15 %-Quote und können sich qualifizieren — NICHT alle I/L-Starter (Malinois,
    Groenendael, „Working"-Border ohne SHSB usw. laufen mit, qualifizieren sich aber nicht).

    Zwei Quellen, in dieser Priorität (analog dem `is_in_season`-Muster der Software):
      1. **Per-Entry-Flag** `entry["bccs_sm"]` — gesetzt per Teilnehmer-Checkbox bzw.
         AOA-Import (Portal→eventexport→Entry). Sobald das Feld bei IRGENDEINEM Eintrag
         vorkommt, gilt der Per-Entry-Modus: ein Eintrag zählt genau dann, wenn
         `entry["bccs_sm"]` truthy ist (nicht markierte Hunde fallen raus).
      2. **Lizenz-Liste** `bccs_sm_config["sm_licenses"]` — Fallback, wenn keine
         Per-Entry-Flags vorhanden sind (z.B. schneller manueller Lizenz-Import am Event).

    Returns:
      - Prädikat `fn(entry) -> bool`, wenn ein Filter aktiv ist.
      - `None`, wenn keine der beiden Quellen etwas liefert → KEIN Filter (alle zählen).
        Abwärtskompatibel für reine Border-Events / Altdaten (kein `bccs_sm`-Feld).
    """
    if _event_has_sm_flags(event):
        return lambda e: bool(e.get("bccs_sm"))

    config = event.get("bccs_sm_config") or {}
    raw = config.get("sm_licenses")
    if raw:
        licenses = {str(l).strip() for l in raw if str(l).strip()}
        if licenses:
            return lambda e: (e.get("Lizenznummer") or "").strip() in licenses

    return None


def _event_has_sm_flags(event: dict) -> bool:
    """True, wenn in irgendeinem BCCS-relevanten Lauf ein Eintrag das Feld `bccs_sm` trägt
    (Key present ⇒ Per-Entry-Modus, unabhängig von True/False)."""
    for run in event.get("runs", []):
        if run.get("kategorie") not in CATEGORIES:
            continue
        if run.get("laufart") not in QUALI_RUN_TYPES:
            continue
        for e in run.get("entries", []):
            if "bccs_sm" in e:
                return True
    return False


def _is_sm_participant(entry: dict, sm_pred) -> bool:
    """True, wenn der Eintrag als SM-Hund zählt (kein Filter aktiv ⇒ immer True)."""
    return True if sm_pred is None else bool(sm_pred(entry))


def _has_raw_result(entries: list[dict]) -> bool:
    """True, wenn mind. ein Eintrag Roh-Ergebnisdaten trägt, die eine Neuberechnung
    erlauben: ein `result`-Dict oder ein top-level `zeit` (so liest sie
    utils._calculate_run_results). Fehlen die Rohdaten (z.B. Unit-Test-Fixtures mit
    nur vorberechneten Feldern), ist kein sinnvoller Recompute möglich → Fallback."""
    for e in entries:
        if "result" in e or "zeit" in e:
            return True
    return False


def _sm_entries_for_run(run: dict, sm_pred, recalc_fn) -> list[dict]:
    """Liefert die für die BCCS-Wertung zählenden Entries EINES Laufs.

    Reglement P.2: nur SM-Hunde zählen. Weil die SCT in Kl.2/3 dynamisch aus der
    schnellsten *berücksichtigten* Zeit abgeleitet wird (utils._calculate_run_results),
    muss die SM-only-Rangliste ihre Zeitfehler/fehler_total NEU über das SM-Feld
    rechnen — sonst stammen sie aus der offenen (Gesamtfeld-)Berechnung und sind falsch.

    - `sm_pred is None`            → kein Filter aktiv (reine Border-Events/Altdaten):
                                      ganzes Feld = SM-Feld, gespeicherte Werte gelten.
    - `recalc_fn is None` ODER keine Rohdaten → Fallback: SM-gefilterte Entries mit
                                      gespeicherten Werten (bisheriges Verhalten, kompatibel).
    - sonst                        → Temp-Lauf (Kopie) NUR mit SM-Entries durch
                                      `recalc_fn` neu rechnen; das Original-Event bleibt
                                      unberührt (die offene Rangliste darf sich nicht ändern).
    """
    entries = run.get("entries", []) or []
    if sm_pred is None:
        return entries
    sm_entries = [e for e in entries if _is_sm_participant(e, sm_pred)]
    if recalc_fn is None or not _has_raw_result(sm_entries):
        return sm_entries
    temp_run = {
        "klasse":    run.get("klasse"),
        "laufart":   run.get("laufart"),
        "laufdaten": copy.deepcopy(run.get("laufdaten", {}) or {}),
        "entries":   copy.deepcopy(sm_entries),
    }
    recalc_fn(temp_run)
    return temp_run["entries"]


def _find_defender(defenders: list[dict], category: str, div_key: str):
    """Sucht den Titelverteidiger für eine bestimmte Division."""
    for d in defenders:
        if (d.get("category") == category and d.get("division") == div_key
                and (d.get("license") or "").strip()):
            return d
    return None


def _collect_division(event: dict, category: str, division_classes: list[str], sm_filter=None, recalc_fn=None):
    """
    Sammelt Quali- und Final-Einträge einer Division (Kategorie + Klassen-Gruppe).

    Returns: (quali_pools, final_pools), je dict laufart → Liste normalisierter Einträge.
    Für Nachwuchs (Klassen 1+2) werden die Einträge je Laufart über die Klassen
    hinweg zu EINEM Pool zusammengefasst. `sm_filter` (optional) beschränkt auf SM-Hunde;
    `recalc_fn` (optional) rechnet die SM-only-Werte neu (SCT aus SM-Feld, s. `_sm_entries_for_run`).
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
        for e in _sm_entries_for_run(run, sm_filter, recalc_fn):
            lic = (e.get("Lizenznummer") or "").strip()
            if not lic:
                continue
            ne = _normalise_entry(e)
            ne["from_class"] = int(cls) if cls.isdigit() else None
            bucket[laufart].append(ne)

    return quali, final


def _collect_class(event: dict, category: str, cls: str, sm_filter=None, recalc_fn=None) -> dict:
    """Quali-Einträge EINER (Kategorie × Klasse) je Laufart (Kl.1/Kl.2 getrennt werten).
    `sm_filter` (optional) beschränkt auf SM-Hunde (Reglement P.2); `recalc_fn` (optional)
    rechnet die SM-only-Werte neu (SCT aus SM-Feld, s. `_sm_entries_for_run`)."""
    quali = {"Agility": [], "Jumping": []}
    for run in event.get("runs", []):
        if run.get("kategorie") != category or run.get("is_final"):
            continue
        if str(run.get("klasse") or "") != cls:
            continue
        laufart = run.get("laufart") or ""
        if laufart not in QUALI_RUN_TYPES:
            continue
        for e in _sm_entries_for_run(run, sm_filter, recalc_fn):
            lic = (e.get("Lizenznummer") or "").strip()
            if not lic:
                continue
            ne = _normalise_entry(e)
            ne["from_class"] = int(cls) if cls.isdigit() else None
            quali[laufart].append(ne)
    return quali


def _defender_started(event: dict, category: str, classes: list[str], lic: str) -> bool:
    """True, wenn der Titelverteidiger in >=1 Quali-Lauf der Division (Kategorie+Klassen) gestartet ist."""
    for run in event.get("runs", []):
        if run.get("kategorie") != category or run.get("is_final"):
            continue
        if str(run.get("klasse") or "") not in classes:
            continue
        if run.get("laufart") not in QUALI_RUN_TYPES:
            continue
        for e in run.get("entries", []):
            if (e.get("Lizenznummer") or "").strip() == lic:
                return True
    return False


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

def _compute_class(quali_pools: dict, quali_order: list[str], qualified: set) -> dict:
    """
    Qualifikation EINER (Kategorie × Klasse): 15 %-Direktquote pro Lauf,
    Doppelqualifikation überspringen, alternierendes Nachrücken zwischen den 2
    Quali-Läufen. Nutzt die division-weite `qualified`-Menge (Titelverteidiger
    ist dort schon enthalten und wird so übersprungen).
    """
    finalists: list[dict] = []

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
    # (finalists enthält hier nur Direkt-Qualifizierte; Titelverteidiger zählt division-weit extra)
    target = sum(run_quota.values())
    remaining = max(0, target - len(finalists))

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
    Rangiert eine Division aus den 2 Finalläufen (Summe Jumping + Agility) gemäss
    Reglement 3.2: nur in BEIDEN Läufen klassierte Teams werden rangiert, nach
      1. kleinerer Summe Gesamtfehlerpunkte (Parcours- + Zeitfehler)
      2. kleinerer Summe Parcoursfehler
      3. kleinerer Summe Laufzeiten
    Gleichstand in allen dreien → ex aequo.

    **DIS im Final = „nicht klassiert"** (User-Entscheid 2026-11-01, bestätigt am
    Reglement): ein Team mit DIS/ABR/DNS in einem Finallauf (oder ohne beide Läufe)
    erhält KEINEN Kombi-Rang und wird unrangiert ans Ende gestellt. Das Reglement
    kennt nur die Summe der zwei sauberen Läufe; die offizielle SportyDog-PDF listet
    Ein-Lauf-DIS zwar auf hinteren Rängen, das ist aber keine reglementarische
    Klassierung. So kann ein DIS-Lauf nie Sieger werden, solange saubere Teams existieren.
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
