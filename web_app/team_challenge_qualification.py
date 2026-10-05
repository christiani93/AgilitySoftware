"""
Team-Challenge – Wertungsberechnung
====================================

Generisches 2er-Team-Format (Erst-Ausgabe: Edelweiss Challenge, LiTyWee,
08.–10.01.2027 — Samstagsspiel). Konzept: `AgilityPortal/KONZEPT_Team-Challenge.md`.

Format:
- **2er-Teams**, beide Hunde müssen derselben Grössenkategorie (S/M/I/L) angehören.
- Zwei Niveaus: **Soft** (Grad/Klasse 1+2) und **Expert** (Grad/Klasse 3).
- Pro Niveau 2 Parcours auf demselben Feld: **Agility** + **Jumping**.
- Ein Teammitglied läuft Agility, das andere Jumping — jeder Lauf separat
  gewertet/gestoppt.
- **Teamergebnis = Summe Fehlerpunkte + Summe Zeiten** der beiden Läufe.
- Rangliste: zuerst Gesamt-Fehlerpunkte, dann Gesamt-Zeit.
- **Separate Rangliste pro Grössenkategorie** → 4 Grössen × 2 Niveaus = 8 Ranglisten.

Datenformat-Erwartungen am `event`-Dict:
  event["teams"]: Liste von Team-Dicts:
    - external_id, name (optional)
    - kategorie:  "Small" | "Medium" | "Intermediate" | "Large"
    - level:      "soft" | "expert"
    - mitglied_agility_lizenz, mitglied_jumping_lizenz
    - source:     "portal" | "software"
  event["runs"]: die 4 Team-Challenge-Läufe tragen `is_team_challenge: True` +
    `team_level: "soft"|"expert"`, `laufart: "Agility"|"Jumping"`
    (Grösse ist hier bewusst NICHT der Lauf-Filter — Grössen sind im selben Lauf
    gemischt, nur die Rangliste wird nach Grösse gesplittet).

Offene Fragen (siehe Konzept §10, Default-Annahmen bis Bestätigung durch
Veranstalter):
  - DIS/Ausfall eines Mitglieds → Team zählt unvollständig weiter (Sentinel-
    Fehler für den fehlenden Lauf), nicht automatisch Totalausschluss.
  - "Fehlerpunkte" = `fehler_total` (inkl. Zeitfehler), analog allen anderen
    Formaten in dieser Codebase.
"""
from __future__ import annotations


LEVELS = ["soft", "expert"]
RUN_TYPES = ["Agility", "Jumping"]
CATEGORIES = ["Small", "Medium", "Intermediate", "Large"]

# Sentinel-Konvention wie in utils._calculate_run_results:
#   998 = noch keine Zeit erfasst (Lauf noch nicht gelaufen)
#   999 = DIS / ABR / DNS / MCT überschritten
NOT_RUN_SENTINEL = 998.0
DIS_SENTINEL = 999.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_team_challenge_results(event: dict) -> list[dict]:
    """
    Berechnet die Team-Ergebnisse für alle Teams eines Events.

    Erwartet, dass die 4 Team-Läufe bereits via `recalc_and_store()` aktuell
    berechnet wurden (fehler_total/zeit_total/platz auf den Entries).

    Returns: flache Liste von Team-Result-Dicts (eines pro Team), je mit
    `rank` **innerhalb der Gruppe (kategorie, level)** befüllt (ex-aequo-fähig).
    Teams ohne jegliche Lauf-Zuordnung (`status == "no_entries"`) bleiben ohne
    `rank` (None).
    """
    team_runs = _collect_team_runs(event)
    results = [
        _build_team_result(team, team_runs)
        for team in event.get("teams", [])
    ]

    for group in _group_keys(results):
        _assign_ranks(_in_group(results, group))

    return results


def group_by_category_and_level(results: list[dict]) -> dict:
    """Gruppiert eine Ergebnisliste nach (kategorie, level) für Dashboard/Export.

    Returns: {(kategorie, level): [sortierte Result-Dicts]}, nur für
    tatsächlich vorkommende Gruppen (keine leeren Platzhalter).
    """
    grouped: dict[tuple[str, str], list[dict]] = {}
    for res in results:
        key = (res["kategorie"], res["level"])
        grouped.setdefault(key, []).append(res)
    for key, rows in grouped.items():
        rows.sort(key=_sort_key)
    return grouped


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _collect_team_runs(event: dict) -> dict:
    """Gruppiert die Team-Challenge-Läufe nach (level, laufart).

    Returns: {"soft": {"Agility": run|None, "Jumping": run|None},
              "expert": {...}}
    """
    by_level: dict[str, dict] = {lvl: {} for lvl in LEVELS}
    for run in event.get("runs", []):
        if not run.get("is_team_challenge"):
            continue
        level = run.get("team_level")
        laufart = run.get("laufart")
        if level in by_level and laufart in RUN_TYPES:
            by_level[level][laufart] = run
    return by_level


def _find_entry(run: dict | None, lizenz: str | None) -> dict | None:
    if not run or not lizenz:
        return None
    lizenz = str(lizenz).strip()
    for entry in run.get("entries", []):
        if (entry.get("Lizenznummer") or "").strip() == lizenz:
            return entry
    return None


def _normalise_member(entry: dict | None) -> dict:
    """Wandelt einen Lauf-Entry in eine normalisierte Teilergebnis-Repräsentation."""
    if entry is None:
        return {
            "lizenz": None, "dog_name": "", "handler_name": "",
            "fehler_total": None, "zeit_total": None, "rank": None,
            "status": "missing",
        }

    fehler_total = _safe_float(entry.get("fehler_total"))
    zeit_total = _safe_float(entry.get("zeit_total"))
    dis_val = entry.get("disqualifikation") or ""

    if fehler_total is None or NOT_RUN_SENTINEL <= fehler_total < DIS_SENTINEL:
        status = "pending"  # Lauf noch nicht gewertet
    elif dis_val in ("DIS", "ABR", "DNS") or (fehler_total is not None and fehler_total >= DIS_SENTINEL):
        status = "dis"
    else:
        status = "ok"

    return {
        "lizenz": (entry.get("Lizenznummer") or "").strip(),
        "dog_name": entry.get("Hundename") or entry.get("dog_name") or "",
        "handler_name": (
            (entry.get("Vorname", "") + " " + entry.get("Nachname", "")).strip()
            or entry.get("handler_name") or entry.get("Hundefuehrer") or ""
        ),
        "fehler_total": fehler_total,
        "zeit_total": zeit_total,
        "rank": entry.get("platz"),
        "status": status,
    }


def _build_team_result(team: dict, team_runs: dict) -> dict:
    level = team.get("level")
    runs_for_level = team_runs.get(level, {})

    agility_entry = _find_entry(runs_for_level.get("Agility"), team.get("mitglied_agility_lizenz"))
    jumping_entry = _find_entry(runs_for_level.get("Jumping"), team.get("mitglied_jumping_lizenz"))

    agility = _normalise_member(agility_entry)
    jumping = _normalise_member(jumping_entry)

    if agility["status"] == "missing" and jumping["status"] == "missing":
        team_status = "no_entries"
    elif agility["status"] == "ok" and jumping["status"] == "ok":
        team_status = "ok"
    elif agility["status"] == "pending" or jumping["status"] == "pending":
        team_status = "pending"
    else:
        team_status = "incomplete"

    total_faults = _contribution(agility) + _contribution(jumping)
    total_time = _contribution(agility, "zeit_total", 999.99) + _contribution(jumping, "zeit_total", 999.99)

    return {
        "external_id": team.get("external_id"),
        "team_name": team.get("name") or "",
        "kategorie": team.get("kategorie"),
        "level": level,
        "agility": agility,
        "jumping": jumping,
        "total_faults": total_faults,
        "total_time": total_time,
        "status": team_status,
        "rank": None,
    }


def _contribution(member: dict, field: str = "fehler_total", sentinel: float = DIS_SENTINEL) -> float:
    """Zahlenwert eines Teilergebnisses für die Summenbildung — fehlende/DIS/
    noch-nicht-gelaufene Läufe tragen den Sentinel bei (schiebt das Team ans
    Gruppenende, ohne die Summe kaputt zu machen)."""
    value = member.get(field)
    if value is None or member.get("status") != "ok":
        return sentinel
    return value


def _sort_key(res: dict):
    return (res["total_faults"], res["total_time"])


def _group_keys(results: list[dict]):
    seen = set()
    keys = []
    for res in results:
        key = (res["kategorie"], res["level"])
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def _in_group(results: list[dict], key) -> list[dict]:
    return [r for r in results if (r["kategorie"], r["level"]) == key]


def _assign_ranks(group: list[dict]) -> None:
    """Ex-aequo-Rangvergabe innerhalb einer Gruppe, analog skbs_sm_qualification.rank_final.
    Teams ohne jegliche Lauf-Zuordnung (`no_entries`) bleiben ohne Rang."""
    rankable = [r for r in group if r["status"] != "no_entries"]
    rankable.sort(key=_sort_key)

    rank = 0
    last_key = None
    for i, res in enumerate(rankable, start=1):
        key = _sort_key(res)
        if key != last_key:
            rank = i
            last_key = key
        res["rank"] = rank


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
