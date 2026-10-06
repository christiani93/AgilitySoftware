"""
KO-Cup Finalisten-Ableitung (Halloween Cup "Schlüssel")
=======================================================

Leitet die Finalisten eines KO-Finales automatisch aus den Turnierläufen ab,
gesteuert durch einen **konfigurierbaren Schlüssel** (Reglement HCS, Blatt
"Schlüssel"). Gegenstück zur Portal-Logik `app/services/cup_qualification.py`,
hier aber offline auf dem Software-Event-Dict (Muster `skbs_sm_qualification.py`).

Schlüssel-Modell (am Event unter ``event["ko_cup"]["qualification"]``; fehlt er,
greift ``DEFAULT_SCHLUESSEL``):

    {
      "runs": [
        { "label": "Tunnellauf",
          "match": {"laufart": "Tunnellauf"},   # welche Läufe zählen
          "split_by_class": false,              # Kl 1-3 KOMBINIERT (eine Rangliste)
          "spots": {"Large": 5, "Intermediate": 3, "Medium": 3, "Small": 3} },
        { "label": "Agility",
          "match": {"laufart": "Agility"},
          "split_by_class": true,               # Kl 1/2/3 GETRENNT
          "spots": {"Large": 3, "Intermediate": 1, "Medium": 1, "Small": 1} },
        { "label": "Jumping", ... gleich wie Agility ... },
      ],
    }

Regeln (Blatt "Schlüssel", Kopftext):
  - "Aus jedem Lauf kann man sich qualifizieren. Dabei sind die Läufe des
    Tunnellaufs am Freitag ... für alle Klassen ... gleich"  → split_by_class=False
    heisst: alle Klassen fliessen in EINE Rangliste pro Kategorie (neu sortiert
    nach fehler_total, zeit_total) — nicht die Einzel-Klassen-Ränge.
  - "Jeder kann sich ... nur einmal für den Final qualifizieren. Bei einer
    Mehrfachqualifikation rückt der nächste noch nicht qualifizierte aus der
    Rangliste nach"  → Dedup pro Kategorie; ein bereits qualifizierter Hund
    verbraucht KEINEN Startplatz, der nächste Nicht-Qualifizierte rückt nach.
  - Manuelle Quellen (Titelverteidiger, Beste Verkleidung, Wildcard) sind NICHT
    lauf-basiert und werden hier nicht erzeugt; sie bleiben als Hand-Einträge
    (``source`` ≠ "run") erhalten und zählen bei der Dedup-Prüfung mit.

Stand 2026 (AT Seeland): der "Open"-Lauf entfällt, kein Lucky-Run/Auffüller →
Default-Schlüssel enthält nur Tunnellauf + Sa Agility + Sa Jumping. Der
definitive Schlüssel wird laut Reglement jährlich nach Anmeldeschluss in
Prozenten neu erstellt → deshalb konfigurierbar pro Event.
"""
from __future__ import annotations

from collections import defaultdict

import ko_cup
from utils import _load_settings, recalc_and_store

CATEGORIES = ["Large", "Intermediate", "Medium", "Small"]

# Quellen, die diese Ableitung erzeugt/ersetzt (re-derivierbar):
RUN_SOURCES = {"run"}
# Manuelle Quellen, die erhalten bleiben und bei der Dedup mitzählen:
MANUAL_SOURCES = {"title_defender", "wildcard", "fillup"}

# noch-nicht-gelaufen (998) / DIS (999) — Sentinels aus utils._calculate_run_results
NOT_RUN_SENTINEL = 998.0

DEFAULT_SCHLUESSEL = {
    "runs": [
        {
            "label": "Tunnellauf",
            "match": {"laufart": "Tunnellauf"},
            "split_by_class": False,
            "spots": {"Large": 5, "Intermediate": 3, "Medium": 3, "Small": 3},
        },
        {
            "label": "Agility",
            "match": {"laufart": "Agility"},
            "split_by_class": True,
            "spots": {"Large": 3, "Intermediate": 1, "Medium": 1, "Small": 1},
        },
        {
            "label": "Jumping",
            "match": {"laufart": "Jumping"},
            "split_by_class": True,
            "spots": {"Large": 3, "Intermediate": 1, "Medium": 1, "Small": 1},
        },
    ],
}

# Kategorie-Normalisierung: Kürzel + Vollnamen → kanonischer Vollname
_CAT_ALIASES = {
    "L": "Large", "LARGE": "Large",
    "I": "Intermediate", "INTERMEDIATE": "Intermediate",
    "M": "Medium", "MEDIUM": "Medium",
    "S": "Small", "SMALL": "Small",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_schluessel(event: dict) -> dict:
    """Schlüssel des Events oder (Kopie des) Default-Schlüssel."""
    ko = event.get("ko_cup") or {}
    schluessel = ko.get("qualification")
    if isinstance(schluessel, dict) and schluessel.get("runs"):
        return schluessel
    import copy
    return copy.deepcopy(DEFAULT_SCHLUESSEL)


def calculate_ko_qualification(event: dict, schluessel: dict | None = None) -> dict:
    """
    Berechnet die lauf-basierten Finalisten pro Kategorie (ohne das Event zu
    verändern — reine Berechnung).

    Returns:
      {
        "derived": {cat: [participant, ...]},   # neu abgeleitet (source="run")
        "manual":  {cat: [participant, ...]},    # erhaltene Hand-Einträge
        "counts":  {cat: {"derived": int, "manual": int, "total": int}},
      }
    participant-Dicts sind kompatibel mit ko_cup.build_bracket (id, dog_name,
    handler_name, license_no, start_number, seeding_rank, draw_number, source)
    und tragen zusätzlich from_class / quali_label (Info/Anzeige).
    """
    schluessel = schluessel or get_schluessel(event)
    settings = _load_settings()

    qualified: dict[str, set[str]] = {cat: set() for cat in CATEGORIES}
    manual_by_cat: dict[str, list[dict]] = {cat: [] for cat in CATEGORIES}

    # Manuelle Finalisten der bestehenden Finals einsammeln → gelten als qualifiziert
    for final in (event.get("ko_cup") or {}).get("finals", []):
        cat = _norm_cat(final.get("category_code"))
        if cat not in CATEGORIES:
            continue
        for p in final.get("participants", []):
            if (p.get("source") or "run") in MANUAL_SOURCES:
                manual_by_cat[cat].append(p)
                key = _participant_key(p)
                if key:
                    qualified[cat].add(key)

    derived_by_cat: dict[str, list[dict]] = {cat: [] for cat in CATEGORIES}

    for cfg in schluessel.get("runs", []):
        _process_config_run(event, cfg, settings, qualified, derived_by_cat)

    counts = {
        cat: {
            "derived": len(derived_by_cat[cat]),
            "manual": len(manual_by_cat[cat]),
            "total": len(derived_by_cat[cat]) + len(manual_by_cat[cat]),
        }
        for cat in CATEGORIES
    }
    return {"derived": derived_by_cat, "manual": manual_by_cat, "counts": counts}


def apply_ko_qualification(event: dict, schluessel: dict | None = None) -> dict:
    """
    Berechnet die Finalisten und schreibt sie in ``event["ko_cup"]["finals"]``:
      - erzeugt fehlende Finals pro Kategorie (mit abgeleiteten Finalisten),
      - ersetzt die bisherigen source="run"-Teilnehmer (re-derivierbar),
      - lässt manuelle Teilnehmer (Titelverteidiger/Verkleidung/Wildcard) stehen,
      - invalidiert ein ggf. bestehendes Bracket (Teilnehmer haben sich geändert).

    Mutiert das Event. Returns das Ergebnis von calculate_ko_qualification plus
    "finals_touched": [cat, ...].
    """
    result = calculate_ko_qualification(event, schluessel)
    derived_by_cat = result["derived"]

    ko = event.setdefault("ko_cup", {})
    ko.setdefault("enabled", True)
    ko.setdefault("finals", [])

    finals_by_cat = {_norm_cat(f.get("category_code")): f for f in ko["finals"]}
    touched: list[str] = []

    for cat in CATEGORIES:
        derived = derived_by_cat.get(cat, [])
        final = finals_by_cat.get(cat)

        if not derived and final is None:
            continue  # keine Finalisten und kein Final → nichts tun

        if final is None:
            final = {
                "id": ko_cup._gen_id("final"),
                "group_label": cat,
                "category_code": cat,
                "class_level": None,
                "participants": [],
                "matchups": [],
                "results": [],
                "is_published": False,
            }
            ko["finals"].append(final)
            finals_by_cat[cat] = final

        # source="run" entfernen, manuelle behalten
        kept = [p for p in final.get("participants", [])
                if (p.get("source") or "run") not in RUN_SOURCES]
        final["participants"] = kept + derived
        # Bracket invalidieren — Teilnehmer haben sich geändert
        final["matchups"] = []
        final["results"] = []
        touched.append(cat)

    result["finals_touched"] = touched
    return result


# ---------------------------------------------------------------------------
# Verarbeitung eines Schlüssel-Laufs
# ---------------------------------------------------------------------------

def _process_config_run(event, cfg, settings, qualified, derived_by_cat) -> None:
    match = cfg.get("match") or {}
    split = bool(cfg.get("split_by_class"))
    spots_cfg = cfg.get("spots") or {}
    label = cfg.get("label") or ""

    runs = [r for r in event.get("runs", []) if _run_matches(r, match)]
    if not runs:
        return

    # Ergebnisse gruppieren: key = (kategorie, klasse|None)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for run in runs:
        computed = recalc_and_store(run, settings)
        for c in computed:
            cat = _norm_cat(_entry_category(c, run))
            if cat not in CATEGORIES:
                continue
            cls = _entry_class(c, run) if split else None
            groups[(cat, cls)].append(c)

    for (cat, cls), entries in groups.items():
        spots = _to_int(spots_cfg.get(cat, 0))
        if spots <= 0:
            continue
        ranked = _rank_combined(entries)

        given = 0
        for e in ranked:
            if given >= spots:
                break
            key = _entry_key(e)
            if not key:
                continue
            if key in qualified[cat]:
                # Doppelqualifikation: Platz NICHT verbrauchen, nächster rückt nach
                continue
            qualified[cat].add(key)
            given += 1
            # from_class = ECHTE Klasse des Hundes (Info/Anzeige), auch beim
            # kombinierten Tunnellauf (wo die Gruppierungs-Klasse cls=None ist).
            derived_by_cat[cat].append(_finalist_from_entry(e, source="run",
                                                            from_class=e.get("Klasse"),
                                                            quali_label=label))


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _run_matches(run: dict, match: dict) -> bool:
    """True, wenn der Lauf alle match-Kriterien erfüllt (case-insensitiv für
    Strings). Unterstützt u.a. {"laufart": "..."} und {"is_tunnel": true}."""
    for field, want in match.items():
        have = run.get(field)
        if isinstance(want, str) and isinstance(have, str):
            if have.strip().lower() != want.strip().lower():
                return False
        elif isinstance(want, bool):
            if bool(have) != want:
                return False
        else:
            if have != want:
                return False
    return True


def _rank_combined(entries: list[dict]) -> list[dict]:
    """Kombinierte Rangliste: DIS/ohne-Zeit raus, aufsteigend nach
    (fehler_total, zeit_total). Gültig für kombinierten Tunnellauf UND für
    einzelne (bereits klassengetrennte) Läufe."""
    valid = []
    for e in entries:
        ft = _to_float(e.get("fehler_total"), NOT_RUN_SENTINEL)
        if ft >= NOT_RUN_SENTINEL:   # 998 noch nicht gelaufen, 999 DIS
            continue
        valid.append(e)
    return sorted(valid, key=lambda e: (_to_float(e.get("fehler_total"), NOT_RUN_SENTINEL),
                                        _to_float(e.get("zeit_total"), NOT_RUN_SENTINEL)))


def _finalist_from_entry(entry: dict, source: str, from_class, quali_label: str) -> dict:
    cls_int = None
    try:
        cls_int = int(from_class) if from_class not in (None, "") else None
    except (TypeError, ValueError):
        cls_int = None
    return {
        "id": ko_cup._gen_id("p"),
        "dog_name": entry.get("Hundename") or entry.get("dog_name") or "",
        "handler_name": _handler_name(entry),
        "license_no": (entry.get("Lizenznummer") or "").strip() or None,
        "start_number": None,          # wird per Los an der Rangverkündigung vergeben
        "seeding_rank": entry.get("platz"),
        "draw_number": None,
        "source": source,
        "from_class": cls_int,
        "quali_label": quali_label,
    }


def _handler_name(entry: dict) -> str:
    fuehrer = (entry.get("Hundefuehrer") or "").strip()
    if fuehrer:
        return fuehrer
    vn = (entry.get("Vorname") or "").strip()
    nn = (entry.get("Nachname") or "").strip()
    combined = f"{vn} {nn}".strip()
    return combined or (entry.get("handler_name") or "")


def _entry_category(entry: dict, run: dict):
    return entry.get("Kategorie") or entry.get("kategorie") or run.get("kategorie")


def _entry_class(entry: dict, run: dict):
    cls = entry.get("Klasse") or entry.get("klasse") or run.get("klasse")
    return str(cls) if cls not in (None, "") else None


def _norm_cat(value) -> str | None:
    if not value:
        return None
    return _CAT_ALIASES.get(str(value).strip().upper())


def _entry_key(entry: dict) -> str | None:
    lic = (entry.get("Lizenznummer") or "").strip()
    if lic:
        return f"lic:{lic}"
    name = (entry.get("Hundename") or entry.get("dog_name") or "").strip().upper()
    return f"dog:{name}" if name else None


def _participant_key(p: dict) -> str | None:
    lic = (p.get("license_no") or "").strip()
    if lic:
        return f"lic:{lic}"
    name = (p.get("dog_name") or "").strip().upper()
    return f"dog:{name}" if name else None


def _to_int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _to_float(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
