"""
make_demo_events.py — erzeugt zwei Demo-Events (NICHT vom Portal importiert) für
lokale Tests:

  1. "DEMO Halloween Cup (KO)"  — KO-Cup (HCS), 2 Finals:
       - Large: 6 Finalisten, Bracket generiert und KOMPLETT durchgespielt
         (Endrangliste + Druck testbar)
       - Small: 4 Finalisten, Bracket generiert, NOCH ungespielt ("running")
  2. "DEMO Edelweiss Team-Challenge" — 6 Teams über 3 Gruppen, inkl. 1 DIS-Fall.

Schreibt nach web_app/data/events.json (Dev/Test-Datenverzeichnis). Bestehende
Events bleiben erhalten; vorhandene DEMO_* werden ersetzt (idempotent).

Aufruf:  python tools/make_demo_events.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_APP = os.path.join(HERE, "..", "web_app")
sys.path.insert(0, WEB_APP)

import ko_cup  # noqa: E402

EVENTS_PATH = os.path.join(WEB_APP, "data", "events.json")


# ---------------------------------------------------------------------------
# KO-Cup (Halloween Cup) Demo
# ---------------------------------------------------------------------------

def _participant(idx, cat, dog, handler, lic, start_no, draw):
    return {
        "id": f"p_{cat[:1].lower()}{idx}",
        "dog_name": dog,
        "handler_name": handler,
        "license_no": lic,
        "start_number": start_no,
        "seeding_rank": idx,
        "draw_number": draw,
        "source": "run",
    }


def _play_out(final):
    """Füllt deterministisch alle besetzten, noch leeren Matchups und rechnet
    das Bracket iterativ bis zum Final durch."""
    def fill_side(side, base):
        # base = Grundzeit; zweiter Lauf etwas anders -> realistische Summe
        side["run1"] = {"time": round(base, 2), "faults": 0, "refusals": 0, "dis": False}
        side["run2"] = {"time": round(base + 0.37, 2), "faults": 0, "refusals": 0, "dis": False}

    for _ in range(10):  # genug Iterationen für jede Bracket-Tiefe
        progressed = False
        for m in final["matchups"]:
            if not m.get("a_id") or not m.get("b_id"):
                continue
            if ko_cup.score_side(m.get("a")) is not None and ko_cup.score_side(m.get("b")) is not None:
                continue
            pa = ko_cup.get_participant(final, m["a_id"])
            pb = ko_cup.get_participant(final, m["b_id"])
            # tiefere Startnummer = minim schneller -> deterministischer Sieger
            sa = (pa or {}).get("start_number") or 50
            sb = (pb or {}).get("start_number") or 50
            fill_side(m["a"], 18.0 + sa * 0.05)
            fill_side(m["b"], 18.0 + sb * 0.05)
            progressed = True
        ko_cup.recompute(final)
        if not progressed or ko_cup.bracket_status(final) == "done":
            break


def _ko_final(category, participants, play=False):
    final = {
        "id": ko_cup._gen_id("final"),
        "group_label": category,
        "category_code": category,
        "class_level": None,
        "participants": participants,
        "matchups": [],
        "results": [],
        "is_published": False,
    }
    final["matchups"] = ko_cup.build_bracket(participants)
    ko_cup.recompute(final)
    if play:
        _play_out(final)
    return final


def build_hcs_demo():
    large = [
        _participant(1, "Large", "Spooky",   "Anna Keller",     "9101", 3,  1),
        _participant(2, "Large", "Pumpkin",  "Beat Müller",     "9102", 7,  2),
        _participant(3, "Large", "Grim",     "Clara Rossi",     "9103", 12, 3),
        _participant(4, "Large", "Zombie",   "Dario Weber",     "9104", 18, 4),
        _participant(5, "Large", "Witch",    "Eva Steiner",     "9105", 21, 5),
        _participant(6, "Large", "Ghost",    "Finn Brun",       "9106", 25, 6),
    ]
    small = [
        _participant(1, "Small", "Mini-Bat",  "Gina Hofer",     "9201", 2,  1),
        _participant(2, "Small", "Skelly",    "Hans Graf",      "9202", 5,  2),
        _participant(3, "Small", "Casper",    "Ida Meier",      "9203", 9,  3),
        _participant(4, "Small", "Hex",       "Jonas Vogt",     "9204", 14, 4),
    ]

    event = {
        "id": "DEMO_HCS",
        "external_id": None,
        "Bezeichnung": "DEMO Halloween Cup (KO)",
        "Datum": "2026-10-31",
        "VeranstalterClubNr": "9999",
        "Turniernummer": "DEMO-HCS",
        "num_rings": 2,
        "runs": [],
        "run_order": [],
        "start_number_schema": {},
        "start_times_by_ring": {"ring_1": "09:00", "ring_2": "09:00"},
        "Veranstaltungsart": "",
        "ko_cup": {
            "enabled": True,
            "finals": [
                _ko_final("Large", large, play=True),
                _ko_final("Small", small, play=False),
            ],
        },
    }
    return event


# ---------------------------------------------------------------------------
# KO-Cup Quali-Demo MIT Läufen (für den "Finalisten ableiten"-Button)
# ---------------------------------------------------------------------------
# Anders als DEMO_HCS (Finals direkt befüllt) trägt dieses Event echte
# Quali-Läufe: Tunnellauf Fr (über Klassen kombiniert), Sa Agility/Jumping je
# Klasse. Damit ist ko_cup_config → "Jetzt ableiten" durchklickbar.

def _q_run(laufart, kategorie, klasse, entries, sct="40"):
    """Ein Quali-Lauf. Grosszügige manuelle SCT (nur für Kl.1 wirksam; Kl.2/3
    leiten die SCT aus der schnellsten Zeit ab) → realistische kleine
    Zeitfehler, Rangfolge deterministisch über (Fehler, Zeit)."""
    return {
        "id": str(uuid.uuid4()),
        "name": f"{laufart} {kategorie} Kl.{klasse}",
        "laufart": laufart,
        "kategorie": kategorie,
        "klasse": str(klasse),
        "entries": entries,
        "laufdaten": {"standardzeit_sct": sct, "auto_dis_on_mct_exceeded": False},
    }


def build_hcs_quali_demo():
    # Doppelqualifikanten (qualifizieren in mehreren Läufen → Dedup/Nachrücken):
    #   L31 "Nightmare" (Large Kl.3) gewinnt Tunnellauf UND Sa-Agility.
    #   S31 "Shadow"    (Small Kl.3) gewinnt Tunnellauf UND Sa-Jumping.
    runs = []

    # ── Freitag Tunnellauf — pro Klasse ein Lauf, Ableitung kombiniert sie ──
    runs += [
        _q_run("Tunnellauf", "Large", 1, [
            _entry("L11", "Casper",    "Anna Keller",  "25.00"),
            _entry("L12", "Bones",     "Beat Müller",  "26.20"),
            _entry("L13", "Specter",   "Clara Rossi",  "27.10", fehler=1),
        ]),
        _q_run("Tunnellauf", "Large", 2, [
            _entry("L21", "Wraith",    "Dario Weber",  "24.60"),
            _entry("L22", "Phantom",   "Eva Steiner",  "25.40"),
        ]),
        _q_run("Tunnellauf", "Large", 3, [
            _entry("L31", "Nightmare", "Finn Brun",    "23.00"),
            _entry("L32", "Reaper",    "Gina Hofer",   "24.10"),
            _entry("L33", "Banshee",   "Hans Graf",    "26.90"),
        ]),
        _q_run("Tunnellauf", "Small", 1, [
            _entry("S11", "Mini-Bat",  "Ida Meier",    "30.00"),
            _entry("S12", "Pebble",    "Jonas Vogt",   "31.20"),
        ]),
        _q_run("Tunnellauf", "Small", 3, [
            _entry("S31", "Shadow",    "Kim Lang",     "28.00"),
            _entry("S32", "Gremlin",   "Lea Frei",     "29.60"),
        ]),
    ]

    # ── Samstag Agility — je Klasse getrennt (split_by_class=True) ──
    runs += [
        _q_run("Agility", "Large", 1, [
            _entry("L11", "Casper",    "Anna Keller",  "28.00"),  # schon via Tunnel → rückt nach
            _entry("L12", "Bones",     "Beat Müller",  "28.90"),
            _entry("L14", "Ghoul",     "Mia Studer",   "30.10"),
        ]),
        _q_run("Agility", "Large", 3, [
            _entry("L31", "Nightmare", "Finn Brun",    "27.00"),  # Doppelquali → Dedup
            _entry("L35", "Mortis",    "Nico Frei",    "28.40"),
            _entry("L36", "Hex",       "Ole Bianchi",  "29.20"),
        ]),
    ]

    # ── Samstag Jumping — je Klasse getrennt ──
    runs += [
        _q_run("Jumping", "Small", 3, [
            _entry("S31", "Shadow",    "Kim Lang",     "26.00"),  # Doppelquali → Dedup
            _entry("S33", "Imp",       "Pia Lehmann",  "27.30"),
            _entry("S34", "Sprite",    "Rolf Senn",    "28.10", fehler=1),
        ]),
    ]

    # Manueller Finalist (Titelverteidiger) — bleibt bei Ableitung erhalten.
    title_defender = {
        "id": "p_title_L",
        "dog_name": "Count Dracula",
        "handler_name": "Vorjahressieger",
        "license_no": "L99",
        "start_number": 1,
        "seeding_rank": None,
        "draw_number": None,
        "source": "title_defender",
    }

    event = {
        "id": "DEMO_HCS_QUALI",
        "external_id": None,
        "Bezeichnung": "DEMO Halloween Cup (Quali-Läufe → Ableiten)",
        "Datum": "2026-10-31",
        "VeranstalterClubNr": "9999",
        "Turniernummer": "DEMO-HCS-Q",
        "num_rings": 2,
        "runs": runs,
        "run_order": [],
        "start_number_schema": {},
        "start_times_by_ring": {"ring_1": "09:00", "ring_2": "09:00"},
        "Veranstaltungsart": "",
        "ko_cup": {
            "enabled": True,
            # Finals bewusst vorbereitet: Large mit manuellem Titelverteidiger,
            # damit die Erhaltung sichtbar ist. Rest legt die Ableitung an.
            "finals": [
                {
                    "id": ko_cup._gen_id("final"),
                    "group_label": "Large",
                    "category_code": "Large",
                    "class_level": None,
                    "participants": [title_defender],
                    "matchups": [],
                    "results": [],
                    "is_published": False,
                },
            ],
        },
    }
    return event


# ---------------------------------------------------------------------------
# Team-Challenge (Edelweiss) Demo
# ---------------------------------------------------------------------------

import uuid  # noqa: E402

LEVELS = ["soft", "expert"]
RUN_TYPES = ["Agility", "Jumping"]
LEVEL_LABELS = {"soft": "Soft (Kl. 1+2)", "expert": "Expert (Kl. 3)"}


def _tc_run(level, laufart):
    return {
        "id": str(uuid.uuid4()),
        "name": f"Team-Challenge {LEVEL_LABELS[level]} – {laufart}",
        "laufart": laufart,
        "kategorie": "Team",
        "klasse": level.capitalize(),           # "Soft"/"Expert" -> manuelle SCT
        "is_team_challenge": True,
        "team_level": level,
        "entries": [],
        # SCT bewusst sehr hoch -> praktisch keine Zeitfehler (Reglement-Erwartung);
        # Rangfolge damit sauber über Parcours-Fehler, dann Rohzeit.
        "laufdaten": {"standardzeit_sct": "999"},
    }


def _entry(lic, dog, handler, zeit, fehler=0, verw=0, dis=None):
    return {
        "Lizenznummer": lic,
        "Hundename": dog,
        "Hundefuehrer": handler,
        "result": {
            "zeit": zeit,
            "fehler": fehler,
            "verweigerungen": verw,
            "disqualifikation": dis,
        },
    }


def _team(name, kat, level, agi_lic, jump_lic):
    return {
        "id": str(uuid.uuid4()),
        "external_id": f"demo_{agi_lic}_{jump_lic}",
        "name": name,
        "kategorie": kat,
        "level": level,
        "mitglied_agility_lizenz": agi_lic,
        "mitglied_jumping_lizenz": jump_lic,
        "source": "software",
    }


def build_edelweiss_demo():
    runs = {(lvl, rt): _tc_run(lvl, rt) for lvl in LEVELS for rt in RUN_TYPES}

    # ── Teams ────────────────────────────────────────────────────────────────
    # Small / soft (2 Teams), Large / soft (2 Teams), Large / expert (2 Teams)
    teams = [
        _team("Edelweiss Small A", "Small", "soft", "9301", "9302"),
        _team("Edelweiss Small B", "Small", "soft", "9303", "9304"),
        _team("Berg Large A",      "Large", "soft", "9305", "9306"),
        _team("Berg Large B",      "Large", "soft", "9307", "9308"),
        _team("Gipfel Expert A",   "Large", "expert", "9309", "9310"),
        _team("Gipfel Expert B",   "Large", "expert", "9311", "9312"),
    ]

    # ── Lauf-Entries (ein Mitglied pro Rolle/Level) ────────────────────────────
    # soft / Agility
    runs[("soft", "Agility")]["entries"] = [
        _entry("9301", "Flocke",  "Lara Amrein",   "28.40", fehler=0),
        _entry("9303", "Yuki",    "Mia Studer",    "30.10", fehler=1),
    ]
    # soft / Jumping
    runs[("soft", "Jumping")]["entries"] = [
        _entry("9302", "Pepe",    "Nico Frei",     "22.90", fehler=0),
        _entry("9304", "Luna",    "Ole Bianchi",   "24.50", fehler=0),
    ]
    # Large / soft laufen im selben soft-Lauf (Grösse im Lauf gemischt):
    runs[("soft", "Agility")]["entries"] += [
        _entry("9305", "Rocky",   "Pia Lehmann",   "27.80", fehler=0),
        _entry("9307", "Thor",    "Rolf Senn",     "26.60", fehler=0),
    ]
    runs[("soft", "Jumping")]["entries"] += [
        _entry("9306", "Bella",   "Sina Kunz",     "21.40", fehler=0),
        _entry("9308", "Max",     "Tim Roth",      "20.90", fehler=0, dis="DIS"),  # DIS-Demo
    ]
    # expert / Agility
    runs[("expert", "Agility")]["entries"] = [
        _entry("9309", "Nala",    "Urs Baumann",   "25.10", fehler=0),
        _entry("9311", "Zorro",   "Vera Hug",      "24.30", fehler=0),
    ]
    # expert / Jumping
    runs[("expert", "Jumping")]["entries"] = [
        _entry("9310", "Kira",    "Walter Moser",  "19.80", fehler=0),
        _entry("9312", "Rex",     "Xenia Good",    "18.90", fehler=1),
    ]

    event = {
        "id": "DEMO_EDELWEISS",
        "external_id": None,
        "Bezeichnung": "DEMO Edelweiss Team-Challenge",
        "Datum": "2027-01-09",
        "VeranstalterClubNr": "9999",
        "Turniernummer": "DEMO-EDW",
        "num_rings": 1,
        "runs": [runs[(lvl, rt)] for lvl in LEVELS for rt in RUN_TYPES],
        "run_order": [],
        "start_number_schema": {},
        "start_times_by_ring": {"ring_1": "09:00"},
        "Veranstaltungsart": "Team-Challenge",
        "teams": teams,
    }
    return event


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if os.path.exists(EVENTS_PATH):
        with open(EVENTS_PATH, encoding="utf-8") as fh:
            events = json.load(fh)
    else:
        events = []

    demo_ids = {"DEMO_HCS", "DEMO_HCS_QUALI", "DEMO_EDELWEISS"}
    events = [e for e in events if e.get("id") not in demo_ids]

    events.append(build_hcs_demo())
    events.append(build_hcs_quali_demo())
    events.append(build_edelweiss_demo())

    with open(EVENTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(events, fh, ensure_ascii=False, indent=2)

    print(f"OK: {len(events)} Events in {EVENTS_PATH}")
    for e in events:
        print(f"  - {e.get('id')}: {e.get('Bezeichnung', e.get('name'))}")


if __name__ == "__main__":
    main()
