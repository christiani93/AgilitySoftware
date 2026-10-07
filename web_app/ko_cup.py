"""
KO-Cup ("American") – Bracket-Engine für Single-Elimination-Finals
==================================================================

Erst-Ausgabe: Halloween Cup (HCS), AT Seeland, 30.10.–01.11.2026 — Final am
Samstag. Offline-first in der AgilitySoftware (Variante B), Zeitmessung via
TIMY über zwei separate Ringserver-PCs.

Reglement-Kern (siehe Memory project-halloween-cup-ko-system):
  - Finalisten werden vom Portal via eventexport geliefert (inkl. Startnummer).
  - Teilnehmerzahl pro Gruppe = 2er-Potenz (Portal füllt auf). Losnummern werden
    an der Rangverkündigung physisch gezogen und hier pro Finalist eingetragen.
  - Runde 1: höchste Losnummer gegen tiefste (1 vs n, 2 vs n-1, …).
  - Jedes Duell = 2 Teams, jedes läuft 2 Läufe (einmal pro Ring, ~12 Hindernisse).
    Tiefere Startnummer startet Ring 1, die andere Ring 2 — Lauf 2 mit Ringwechsel.
  - Wertung pro Team: Summe der beiden Laufzeiten
    + 2 s pro Fehler + 2 s pro Verweigerung + 5 s pro DIS (pro Lauf).
    Tiefere Gesamtzeit gewinnt. Gleichstand → kein Auto-Sieger (manuell).
  - Single-Elimination. NUR Halbfinal-Verlierer spielen um Platz 3, sonst raus.
  - Nichterscheinen/Rückzug (Forfeit) → Gegner automatisch weiter.

Datenformat am `event`-Dict:
  event["ko_cup"] = {
      "enabled": true,
      "finals": [ <final-dict>, ... ],
  }

Ein <final-dict> (ein Finale pro Gruppe, HCS = pro Grössenkategorie):
  {
    "id": "<stabil>",
    "group_label": "Large",
    "category_code": "Large",
    "class_level": None,            # HCS: Finals pro Kategorie, nicht pro Klasse
    "participants": [ <participant>, ... ],
    "matchups":     [ <matchup>, ... ],   # kompletter Baum (von build_bracket)
    "results":      [ {"participant_id": id, "rank": int}, ... ],
    "is_published": false,
  }

<participant>:
  { "id", "dog_name", "handler_name", "license_no",
    "start_number": int|None,       # TRAGEND: steuert Ring-Zuteilung
    "seeding_rank": int|None,       # Quali-Rang (nur Info / Freilos-Tiebreak)
    "draw_number":  int|None,       # Losnummer (in der Software eingetragen)
    "source": "run"|"fillup"|"title_defender"|"wildcard" }

<matchup>:
  { "id", "round_no", "matchup_no",
    "matchup_type": "winner"|"third_place",
    "a_id", "b_id",                 # Teilnehmer-IDs (None bis aufgelöst)
    "a_source", "b_source",         # {"matchup_id":.., "take":"winner"|"loser"} | None
    "a": {"run1": <run>, "run2": <run>},   # <run>: {time, faults, refusals, dis}
    "b": {"run1": <run>, "run2": <run>},
    "forfeit_id": None,             # dieser Teilnehmer ist zurückgetreten
    "manual_winner_id": None,       # manueller Sieger (Gleichstand / Sonderfall)
    "winner_id": None, "loser_id": None }
"""
from __future__ import annotations

import math
import uuid

# Straffsekunden (Reglement HCS)
PEN_FAULT = 2.0      # pro Fehler
PEN_REFUSAL = 2.0    # pro Verweigerung
PEN_DIS = 5.0        # pro DIS (disqualifiziert, aber nicht ausgeschieden)

# Anzeige-/Ablauf-Reihenfolge der Kategorien: Small zuerst, Large zuletzt.
# Begruendung: je groesser die Kategorie, desto mehr Laeufer -> der Large-Final
# ist das Highlight und laeuft als grosses Finale ganz am Schluss (S-M-I-L).
# Betrifft NUR Anzeige/Sortierung (Config-Liste, API-State fuer Ring/Live,
# Ranglisten) -- NICHT die Bracket-Mathematik (die laeuft ueber draw_number).
CATEGORY_ORDER = ["Small", "Medium", "Intermediate", "Large"]


# ---------------------------------------------------------------------------
# Hilfsfunktionen: 2er-Potenz, IDs, Rundennamen
# ---------------------------------------------------------------------------

def next_power_of_two(n: int) -> int:
    """Nächste 2er-Potenz >= n. Minimum 2."""
    if n <= 2:
        return 2
    return 2 ** math.ceil(math.log2(n))


def _gen_id(prefix: str = "ko") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def round_label(round_no: int, rounds_total: int, matchup_type: str = "winner") -> str:
    """Menschenlesbarer Rundenname (de)."""
    if matchup_type == "third_place":
        return "Spiel um Platz 3"
    offset = rounds_total - round_no
    names = {0: "Final", 1: "Halbfinal", 2: "Viertelfinal", 3: "Achtelfinal"}
    return names.get(offset, f"Runde {round_no}")


def _new_run() -> dict:
    return {"time": None, "faults": 0, "refusals": 0, "dis": False}


def _new_side() -> dict:
    return {"run1": _new_run(), "run2": _new_run()}


def _new_matchup(round_no, matchup_no, matchup_type="winner",
                 a_id=None, b_id=None, a_source=None, b_source=None) -> dict:
    return {
        "id": _gen_id("m"),
        "round_no": round_no,
        "matchup_no": matchup_no,
        "matchup_type": matchup_type,
        "a_id": a_id,
        "b_id": b_id,
        "a_source": a_source,
        "b_source": b_source,
        "a": _new_side(),
        "b": _new_side(),
        "forfeit_id": None,
        "manual_winner_id": None,
        "winner_id": None,
        "loser_id": None,
    }


# ---------------------------------------------------------------------------
# Bracket aufbauen (vollständiger Baum, Platzhalter für Folgerunden)
# ---------------------------------------------------------------------------

def build_bracket(participants: list[dict]) -> list[dict]:
    """
    Erzeugt den kompletten Bracket-Baum aus Teilnehmern mit Losnummern.

    - Teilnehmer werden nach Losnummer sortiert; auf nächste 2er-Potenz mit
      Freilos (None) aufgefüllt.
    - Runde 1: tiefste gegen höchste Losnummer (Position i vs size-1-i).
    - Folgerunden als leere Matchups mit Quellen-Verknüpfung (Sieger rücken nach).
    - Ab 4 Teilnehmern: Spiel um Platz 3 (Halbfinal-Verlierer).

    Freilos: ist ein Teilnehmer in Runde 1 gegen None gelost, rückt er
    automatisch weiter (Bye).

    Returns: flache Liste aller Matchups (round_no aufsteigend).
    """
    ranked = sorted(
        participants,
        key=lambda p: (p.get("draw_number") is None, p.get("draw_number") or 0),
    )
    n = len(ranked)
    if n < 2:
        return []

    size = next_power_of_two(n)
    rounds_total = int(math.log2(size))
    slots = ranked + [None] * (size - n)

    matchups: list[dict] = []

    # Runde 1 – reale Paarungen (tiefste vs höchste Losnummer)
    prev: list[dict] = []
    for i in range(size // 2):
        a = slots[i]
        b = slots[size - 1 - i]
        m = _new_matchup(
            round_no=1, matchup_no=i + 1,
            a_id=(a["id"] if a else None),
            b_id=(b["id"] if b else None),
        )
        matchups.append(m)
        prev.append(m)

    # Folgerunden – leere Matchups, Sieger der Vorrunde rücken nach
    for r in range(2, rounds_total + 1):
        cur: list[dict] = []
        for j in range(len(prev) // 2):
            src_a, src_b = prev[2 * j], prev[2 * j + 1]
            m = _new_matchup(
                round_no=r, matchup_no=j + 1,
                a_source={"matchup_id": src_a["id"], "take": "winner"},
                b_source={"matchup_id": src_b["id"], "take": "winner"},
            )
            matchups.append(m)
            cur.append(m)
        prev = cur

    # Spiel um Platz 3 – Verlierer der beiden Halbfinals (nur ab 4 Teilnehmern)
    if rounds_total >= 2:
        semis = [m for m in matchups if m["round_no"] == rounds_total - 1]
        if len(semis) == 2:
            m = _new_matchup(
                round_no=rounds_total, matchup_no=2, matchup_type="third_place",
                a_source={"matchup_id": semis[0]["id"], "take": "loser"},
                b_source={"matchup_id": semis[1]["id"], "take": "loser"},
            )
            matchups.append(m)

    return matchups


# ---------------------------------------------------------------------------
# Wertung eines Duells
# ---------------------------------------------------------------------------

def score_side(side: dict | None) -> float | None:
    """
    Gesamtzeit einer Seite über beide Läufe inkl. Straffsekunden.
    Gibt None zurück, solange nicht beide Läufe eine Zeit haben.
    """
    if not side:
        return None
    total = 0.0
    for key in ("run1", "run2"):
        run = side.get(key) or {}
        t = run.get("time")
        if t is None:
            return None
        total += float(t)
        total += (run.get("faults") or 0) * PEN_FAULT
        total += (run.get("refusals") or 0) * PEN_REFUSAL
        if run.get("dis"):
            total += PEN_DIS
    return round(total, 3)


def _is_bye(matchup: dict, side: str) -> bool:
    """True, wenn diese Seite ein Freilos ist (Runde 1, kein Quell-Matchup,
    kein Teilnehmer)."""
    return (
        matchup.get(f"{side}_source") is None
        and matchup.get(f"{side}_id") is None
    )


def compute_winner(matchup: dict) -> tuple[str | None, str | None]:
    """
    Ermittelt (winner_id, loser_id) für ein Matchup.

    Reihenfolge der Entscheidung:
      1. Freilos (Bye): die besetzte Seite gewinnt.
      2. Manueller Sieger (Gleichstand / Sonderfall).
      3. Forfeit (Rücktritt/Nichterscheinen): Gegner gewinnt.
      4. Zeitauswertung: tiefere Gesamtzeit gewinnt. Gleichstand → kein Sieger.

    Gibt (None, None) zurück, wenn (noch) nicht entscheidbar.
    """
    a_id, b_id = matchup.get("a_id"), matchup.get("b_id")

    # 1. Freilos
    a_bye, b_bye = _is_bye(matchup, "a"), _is_bye(matchup, "b")
    if a_bye and not b_bye and b_id:
        return b_id, None
    if b_bye and not a_bye and a_id:
        return a_id, None

    # Beide Seiten müssen besetzt sein, um ein echtes Duell zu werten
    if not a_id or not b_id:
        return None, None

    # 2. Manueller Sieger
    mw = matchup.get("manual_winner_id")
    if mw in (a_id, b_id):
        return mw, (b_id if mw == a_id else a_id)

    # 3. Forfeit
    ff = matchup.get("forfeit_id")
    if ff == a_id:
        return b_id, a_id
    if ff == b_id:
        return a_id, b_id

    # 4. Zeitauswertung
    ta = score_side(matchup.get("a"))
    tb = score_side(matchup.get("b"))
    if ta is None or tb is None:
        return None, None
    if ta < tb:
        return a_id, b_id
    if tb < ta:
        return b_id, a_id
    return None, None  # Gleichstand → manuelle Entscheidung nötig


def is_tie(matchup: dict) -> bool:
    """True, wenn beide Seiten fertig gelaufen sind, die Gesamtzeiten gleich
    sind und (noch) kein manueller Sieger gesetzt wurde."""
    if matchup.get("manual_winner_id") or matchup.get("forfeit_id"):
        return False
    ta = score_side(matchup.get("a"))
    tb = score_side(matchup.get("b"))
    return ta is not None and tb is not None and ta == tb


# ---------------------------------------------------------------------------
# Bracket neu berechnen (Sieger auflösen, Teilnehmer nachrücken)
# ---------------------------------------------------------------------------

def _take(by_id: dict, source: dict | None) -> str | None:
    """Liefert Gewinner- bzw. Verlierer-ID des Quell-Matchups (oder None)."""
    if not source:
        return None
    src = by_id.get(source.get("matchup_id"))
    if not src:
        return None
    return src["winner_id"] if source.get("take") == "winner" else src["loser_id"]


def recompute(final: dict) -> dict:
    """
    Löst den gesamten Bracket-Baum auf: füllt a_id/b_id aus Quell-Matchups,
    berechnet winner_id/loser_id jedes Matchups in Rundenreihenfolge und
    aktualisiert die Endrangliste.

    Idempotent — kann nach jedem Ergebnis-Eintrag aufgerufen werden.
    """
    matchups = final.get("matchups", [])
    by_id = {m["id"]: m for m in matchups}

    # Frühe Runden zuerst; innerhalb einer Runde zuerst 'winner', dann 'third_place'
    ordered = sorted(
        matchups,
        key=lambda m: (m["round_no"], m["matchup_type"] != "winner", m["matchup_no"]),
    )
    for m in ordered:
        if m.get("a_source"):
            m["a_id"] = _take(by_id, m["a_source"])
        if m.get("b_source"):
            m["b_id"] = _take(by_id, m["b_source"])
        w, l = compute_winner(m)
        m["winner_id"] = w
        m["loser_id"] = l

    final["results"] = compute_results(final)
    return final


# ---------------------------------------------------------------------------
# Endrangliste
# ---------------------------------------------------------------------------

def compute_results(final: dict) -> list[dict]:
    """
    Erzeugt die Schlussrangliste.

    Plätze 1–4 exakt aus Final + Spiel um Platz 3. Übrige Teilnehmer nach
    Ausscheide-Runde gruppiert (später ausgeschieden = besser; Gleichstand
    innerhalb einer Runde → gleicher Rang).

    Returns: [{"participant_id": id, "rank": int}, ...] nur für Teilnehmer,
    deren Platzierung feststeht.
    """
    matchups = final.get("matchups", [])
    if not matchups:
        return []
    rounds_total = max(m["round_no"] for m in matchups)

    results: dict[str, int] = {}

    # Final (round == rounds_total, type winner)
    final_m = next(
        (m for m in matchups
         if m["round_no"] == rounds_total and m["matchup_type"] == "winner"),
        None,
    )
    if final_m and final_m.get("winner_id"):
        results[final_m["winner_id"]] = 1
        if final_m.get("loser_id"):
            results[final_m["loser_id"]] = 2

    # Spiel um Platz 3
    third_m = next((m for m in matchups if m["matchup_type"] == "third_place"), None)
    if third_m and third_m.get("winner_id"):
        results[third_m["winner_id"]] = 3
        if third_m.get("loser_id"):
            results[third_m["loser_id"]] = 4

    # Übrige Verlierer nach Ausscheide-Runde (Halbfinal-Verlierer sind via
    # Spiel um Platz 3 bereits auf 3/4 und werden hier übersprungen)
    semifinal_round = rounds_total - 1 if rounds_total >= 2 else None
    exit_round: dict[str, int] = {}
    for m in matchups:
        lid = m.get("loser_id")
        if not lid or lid in results:
            continue
        # Halbfinal-Verlierer nur überspringen, wenn ein Spiel um Platz 3 existiert
        if third_m is not None and m["round_no"] == semifinal_round and m["matchup_type"] == "winner":
            continue
        # spätere Ausscheide-Runde = besser
        exit_round[lid] = max(exit_round.get(lid, 0), m["round_no"])

    # Gruppieren: höhere Ausscheide-Runde = besserer Rang; Ties teilen Rang
    taken = len(results)
    next_rank = taken + 1
    for rnd in sorted(set(exit_round.values()), reverse=True):
        group = [pid for pid, r in exit_round.items() if r == rnd]
        for pid in group:
            results[pid] = next_rank
        next_rank += len(group)

    return [{"participant_id": pid, "rank": rank}
            for pid, rank in sorted(results.items(), key=lambda kv: kv[1])]


# ---------------------------------------------------------------------------
# Ring-Zuteilung (2 Ringe) – tiefere Startnummer startet Ring 1
# ---------------------------------------------------------------------------

def ring_assignment(final: dict, matchup: dict) -> dict:
    """
    Ermittelt für ein Duell, wer in welchem Lauf auf welchem Ring startet.

    Tiefere Startnummer → Lauf 1 auf Ring 1, Lauf 2 auf Ring 2 (Ringwechsel).
    Fehlt eine Startnummer, gilt die vorhandene als 'tiefer'; fehlen beide,
    startet Seite A auf Ring 1.

    Returns: {"a": {"run1": ring, "run2": ring}, "b": {...}}
    """
    pa = get_participant(final, matchup.get("a_id"))
    pb = get_participant(final, matchup.get("b_id"))
    sa = pa.get("start_number") if pa else None
    sb = pb.get("start_number") if pb else None

    # a_first = True → Seite A startet auf Ring 1
    if sa is None and sb is None:
        a_first = True
    elif sb is None:
        a_first = True
    elif sa is None:
        a_first = False
    else:
        a_first = sa <= sb

    a_ring1 = 1 if a_first else 2
    b_ring1 = 2 if a_first else 1
    return {
        "a": {"run1": a_ring1, "run2": 3 - a_ring1},
        "b": {"run1": b_ring1, "run2": 3 - b_ring1},
    }


# ---------------------------------------------------------------------------
# Zugriff / Status
# ---------------------------------------------------------------------------

def get_participant(final: dict, pid: str | None) -> dict | None:
    if not pid:
        return None
    return next((p for p in final.get("participants", []) if p.get("id") == pid), None)


def bracket_status(final: dict) -> str:
    """'setup' (kein Bracket), 'running' (Bracket da, Final offen) oder
    'done' (Final entschieden)."""
    matchups = final.get("matchups", [])
    if not matchups:
        return "setup"
    rounds_total = max(m["round_no"] for m in matchups)
    final_m = next(
        (m for m in matchups
         if m["round_no"] == rounds_total and m["matchup_type"] == "winner"),
        None,
    )
    if final_m and final_m.get("winner_id"):
        return "done"
    return "running"


def matchups_by_round(final: dict) -> list[tuple[int, str, list[dict]]]:
    """Gruppiert Matchups für die Anzeige: Liste von
    (round_no, label, [matchups]) in Spielreihenfolge."""
    matchups = final.get("matchups", [])
    if not matchups:
        return []
    rounds_total = max(m["round_no"] for m in matchups)
    buckets: dict[tuple, list] = {}
    for m in matchups:
        key = (m["round_no"], m["matchup_type"])
        buckets.setdefault(key, []).append(m)
    out = []
    for (rnd, mtype) in sorted(buckets.keys(), key=lambda k: (k[0], k[1] != "winner")):
        label = round_label(rnd, rounds_total, mtype)
        ms = sorted(buckets[(rnd, mtype)], key=lambda m: m["matchup_no"])
        out.append((rnd, label, ms))
    return out
