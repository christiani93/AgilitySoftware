"""
Pure-Python-Tests für die KO-Cup-Finalisten-Ableitung (Halloween Cup Schlüssel).

Abgedeckt:
- Tunnellauf: Kl 1-3 KOMBINIERT zu einer Rangliste pro Kategorie (tiefere Klasse
  mit besserer Zeit schlägt höhere Klasse), Spots pro Kategorie (L vs IMS).
- Samstag Agility/Jumping: split_by_class → pro Klasse eigene Top-N.
- Doppelqualifikation: bereits (via Tunnellauf) qualifizierter Hund wird im
  Agility-Lauf übersprungen, verbraucht KEINEN Platz, nächster rückt nach.
- DIS-Einträge qualifizieren nicht.
- Manuelle Finalisten (Titelverteidiger) bleiben erhalten und zählen bei der
  Dedup mit (kein Doppel-Eintrag).
- apply_ko_qualification: Finals pro Kategorie, Bracket invalidiert, source="run"
  ersetzt / manuelle behalten.
"""
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
WEB_APP_PATH = os.path.join(PROJECT_ROOT, "web_app")
if WEB_APP_PATH not in sys.path:
    sys.path.insert(0, WEB_APP_PATH)

import ko_qualification as koq  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures / Helfer
# ---------------------------------------------------------------------------

def _entry(lic, dog, kat, cls, zeit, fehler=0, verw=0, dis=None, handler=None):
    return {
        "Lizenznummer": lic,
        "Hundename": dog,
        "Hundefuehrer": handler or f"HF {dog}",
        "Kategorie": kat,
        "Klasse": str(cls),
        "result": {
            "zeit": zeit,
            "fehler": fehler,
            "verweigerungen": verw,
            "disqualifikation": dis,
        },
    }


def _run(laufart, kategorie, klasse, entries, laufdaten=None):
    return {
        "id": f"{laufart}_{kategorie}_{klasse}",
        "name": f"{laufart} {kategorie} {klasse}",
        "laufart": laufart,
        "kategorie": kategorie,
        "klasse": str(klasse),
        "entries": entries,
        # hohe manuelle SCT -> keine Zeitfehler, deterministisch nach Zeit
        "laufdaten": laufdaten or {"standardzeit_sct": "999"},
    }


def _names(parts):
    return [p["dog_name"] for p in parts]


# ---------------------------------------------------------------------------
# Tunnellauf: kombinierte Rangliste über Klassen
# ---------------------------------------------------------------------------

def test_tunnellauf_kombiniert_ueber_klassen():
    # Ein Tunnellauf-Lauf mit Large-Hunden aus Kl 1/2/3 gemischt.
    tunnel = _run("Tunnellauf", "Large", "1-3", [
        _entry("L1", "Alpha", "Large", 1, 30.0),
        _entry("L2", "Bravo", "Large", 2, 28.0),   # Kl2, schneller als Kl1
        _entry("L3", "Charlie", "Large", 3, 26.0),  # Kl3, am schnellsten
        _entry("L4", "Delta", "Large", 1, 31.0),
        _entry("L5", "Echo", "Large", 2, 32.0),
        _entry("L6", "Foxtrot", "Large", 3, 33.0),
    ])
    event = {"runs": [tunnel]}
    schluessel = {"runs": [{
        "label": "Tunnellauf", "match": {"laufart": "Tunnellauf"},
        "split_by_class": False, "spots": {"Large": 5, "Intermediate": 3,
                                           "Medium": 3, "Small": 3},
    }]}
    res = koq.calculate_ko_qualification(event, schluessel)
    large = res["derived"]["Large"]
    # Top 5 nach Zeit, klassenübergreifend: Charlie(26) Bravo(28) Alpha(30) Delta(31) Echo(32)
    assert _names(large) == ["Charlie", "Bravo", "Alpha", "Delta", "Echo"]
    # Foxtrot (33.0) fällt raus (nur 5 Plätze)
    assert "Foxtrot" not in _names(large)
    # from_class korrekt mitgeführt (Charlie aus Klasse 3)
    assert large[0]["from_class"] == 3
    assert large[0]["seeding_rank"] == 1  # Platz in der kombinierten Rangliste


def test_tunnellauf_spots_pro_kategorie_L_vs_IMS():
    tunnel = _run("Tunnellauf", "mixed", "1-3", [
        _entry("L1", "LA", "Large", 1, 20.0),
        _entry("L2", "LB", "Large", 2, 21.0),
        _entry("L3", "LC", "Large", 3, 22.0),
        _entry("L4", "LD", "Large", 1, 23.0),
        _entry("S1", "SA", "Small", 1, 20.0),
        _entry("S2", "SB", "Small", 2, 21.0),
        _entry("S3", "SC", "Small", 3, 22.0),
        _entry("S4", "SD", "Small", 1, 23.0),
    ])
    event = {"runs": [tunnel]}
    res = koq.calculate_ko_qualification(event)  # Default-Schlüssel
    # Large: 5 Spots, aber nur 4 Hunde -> alle 4
    assert _names(res["derived"]["Large"]) == ["LA", "LB", "LC", "LD"]
    # Small: 3 Spots -> Top 3
    assert _names(res["derived"]["Small"]) == ["SA", "SB", "SC"]


# ---------------------------------------------------------------------------
# Samstag Agility/Jumping: split_by_class
# ---------------------------------------------------------------------------

def test_agility_split_by_class():
    runs = [
        _run("Agility", "Large", 1, [
            _entry("A", "L1a", "Large", 1, 20.0),
            _entry("B", "L1b", "Large", 1, 21.0),
            _entry("C", "L1c", "Large", 1, 22.0),
            _entry("D", "L1d", "Large", 1, 23.0),  # Platz 4 -> raus (nur 3)
        ]),
        _run("Agility", "Large", 2, [
            _entry("E", "L2a", "Large", 2, 20.0),
            _entry("F", "L2b", "Large", 2, 21.0),
        ]),
        _run("Agility", "Medium", 1, [
            _entry("G", "M1a", "Medium", 1, 20.0),
            _entry("H", "M1b", "Medium", 1, 21.0),  # Medium: nur 1 Spot -> raus
        ]),
    ]
    event = {"runs": runs}
    res = koq.calculate_ko_qualification(event)
    large = _names(res["derived"]["Large"])
    # Kl1 Top3 + Kl2 Top2 (hier nur 2 vorhanden)
    assert set(large) == {"L1a", "L1b", "L1c", "L2a", "L2b"}
    assert "L1d" not in large
    # Medium: 1 Spot
    assert _names(res["derived"]["Medium"]) == ["M1a"]


# ---------------------------------------------------------------------------
# Doppelqualifikation: nächster rückt nach
# ---------------------------------------------------------------------------

def test_doppelquali_naechster_rueckt_nach():
    # "Star" gewinnt den Tunnellauf UND den Agility-Kl2-Lauf.
    tunnel = _run("Tunnellauf", "Large", "1-3", [
        _entry("STAR", "Star", "Large", 2, 25.0),
    ])
    agi = _run("Agility", "Large", 2, [
        _entry("STAR", "Star", "Large", 2, 20.0),   # Platz 1 — schon via Tunnel quali
        _entry("B", "Second", "Large", 2, 21.0),    # Platz 2
        _entry("C", "Third", "Large", 2, 22.0),     # Platz 3
        _entry("D", "Fourth", "Large", 2, 23.0),    # Platz 4
    ])
    event = {"runs": [tunnel, agi]}
    res = koq.calculate_ko_qualification(event)
    large = _names(res["derived"]["Large"])
    # Star nur EINMAL (aus Tunnellauf). Agility Kl2 hat 3 Spots: Star übersprungen,
    # dafür Second/Third/Fourth -> Platz verbraucht NICHT auf Star.
    assert large.count("Star") == 1
    assert "Second" in large and "Third" in large and "Fourth" in large


def test_dis_qualifiziert_nicht():
    agi = _run("Agility", "Medium", 1, [
        _entry("A", "Winner", "Medium", 1, 20.0, dis="DIS"),  # DIS -> raus
        _entry("B", "Runner", "Medium", 1, 25.0),
    ])
    event = {"runs": [agi]}
    res = koq.calculate_ko_qualification(event)
    # Medium: 1 Spot -> geht an Runner (Winner ist DIS)
    assert _names(res["derived"]["Medium"]) == ["Runner"]


# ---------------------------------------------------------------------------
# Manuelle Finalisten
# ---------------------------------------------------------------------------

def test_manueller_titelverteidiger_bleibt_und_dedupt():
    # Titelverteidiger "Champ" liegt bereits im Final (manuell).
    agi = _run("Agility", "Large", 3, [
        _entry("CH", "Champ", "Large", 3, 20.0),   # würde Platz 1 holen
        _entry("B", "Next", "Large", 3, 21.0),
        _entry("C", "Third", "Large", 3, 22.0),
        _entry("D", "Fourth", "Large", 3, 23.0),
    ])
    event = {
        "runs": [agi],
        "ko_cup": {"enabled": True, "finals": [{
            "id": "final_large", "category_code": "Large", "group_label": "Large",
            "participants": [{
                "id": "p_champ", "dog_name": "Champ", "handler_name": "HF Champ",
                "license_no": "CH", "source": "title_defender",
            }],
            "matchups": [], "results": [], "is_published": False,
        }]},
    }
    res = koq.calculate_ko_qualification(event)
    large = _names(res["derived"]["Large"])
    # Champ ist schon (manuell) qualifiziert -> nicht erneut abgeleitet,
    # Platz rückt nach: 3 Spots gehen an Next/Third/Fourth.
    assert "Champ" not in large
    assert large == ["Next", "Third", "Fourth"]
    assert res["counts"]["Large"]["manual"] == 1
    assert res["counts"]["Large"]["total"] == 4


def test_apply_schreibt_finals_und_invalidiert_bracket():
    agi = _run("Agility", "Large", 1, [
        _entry("A", "L1a", "Large", 1, 20.0),
        _entry("B", "L1b", "Large", 1, 21.0),
    ])
    event = {
        "runs": [agi],
        "ko_cup": {"enabled": True, "finals": [{
            "id": "final_large", "category_code": "Large", "group_label": "Large",
            "participants": [
                {"id": "p_champ", "dog_name": "Champ", "license_no": "CH",
                 "source": "title_defender"},
                {"id": "p_old", "dog_name": "OldRun", "license_no": "OLD",
                 "source": "run"},   # alte Ableitung -> muss ersetzt werden
            ],
            "matchups": [{"id": "m1"}],   # bestehendes Bracket -> muss weg
            "results": [{"participant_id": "x", "rank": 1}],
            "is_published": False,
        }]},
    }
    koq.apply_ko_qualification(event)
    final = event["ko_cup"]["finals"][0]
    names = [p["dog_name"] for p in final["participants"]]
    # manueller Titelverteidiger bleibt, alte source="run" ersetzt durch L1a/L1b
    assert "Champ" in names
    assert "OldRun" not in names
    assert "L1a" in names and "L1b" in names
    # Bracket invalidiert
    assert final["matchups"] == []
    assert final["results"] == []


def test_apply_legt_fehlendes_final_an():
    tunnel = _run("Tunnellauf", "Small", "1-3", [
        _entry("S1", "SA", "Small", 1, 20.0),
        _entry("S2", "SB", "Small", 2, 21.0),
    ])
    event = {"runs": [tunnel]}   # noch kein ko_cup
    koq.apply_ko_qualification(event)
    finals = event["ko_cup"]["finals"]
    small = next(f for f in finals if f["category_code"] == "Small")
    assert {p["dog_name"] for p in small["participants"]} == {"SA", "SB"}


# ---------------------------------------------------------------------------
# ranking_tables: Anzeige-Sicht (kombinierte Rangliste / Status-Markierung)
# ---------------------------------------------------------------------------

def _quali_names(block):
    """Alle als 'quali' markierten Hunde über alle Kategorien/Subtabellen."""
    out = []
    for tbl in block["tables"].values():
        for sub in tbl["subtables"]:
            out += [r["dog_name"] for r in sub["rows"] if r["status"] == "quali"]
    return out


def test_ranking_tables_tunnellauf_kombiniert_und_quali_markiert():
    tunnel = _run("Tunnellauf", "Large", "1-3", [
        _entry("L1", "Alpha", "Large", 1, 30.0),
        _entry("L2", "Bravo", "Large", 2, 28.0),
        _entry("L3", "Charlie", "Large", 3, 26.0),
        _entry("L4", "Delta", "Large", 1, 31.0),
        _entry("L5", "Echo", "Large", 2, 32.0),
        _entry("L6", "Foxtrot", "Large", 3, 33.0),
    ])
    event = {"runs": [tunnel]}
    schluessel = {"runs": [{
        "label": "Tunnellauf", "match": {"laufart": "Tunnellauf"},
        "split_by_class": False, "spots": {"Large": 5, "Intermediate": 3,
                                           "Medium": 3, "Small": 3},
    }]}
    blocks = koq.ranking_tables(event, schluessel)
    assert len(blocks) == 1
    block = blocks[0]
    assert block["label"] == "Tunnellauf"
    large = block["tables"]["Large"]
    assert large["combined"] is True
    # kombiniert: GENAU eine Subtabelle (alle Klassen zusammen)
    assert len(large["subtables"]) == 1
    rows = large["subtables"][0]["rows"]
    # alle 6 Teams gelistet, nach Zeit sortiert, Rang 1..6
    assert [r["dog_name"] for r in rows] == ["Charlie", "Bravo", "Alpha", "Delta", "Echo", "Foxtrot"]
    assert [r["rank"] for r in rows] == [1, 2, 3, 4, 5, 6]
    # Top 5 = quali, Foxtrot = none
    assert rows[5]["status"] == "none"
    # Invariante: quali-Zeilen == abgeleitete Finalisten
    derived = _names(koq.calculate_ko_qualification(event, schluessel)["derived"]["Large"])
    assert _quali_names(block) == derived == ["Charlie", "Bravo", "Alpha", "Delta", "Echo"]


def test_ranking_tables_agility_split_subtabellen_pro_klasse():
    runs = [
        _run("Agility", "Large", 1, [
            _entry("A", "L1a", "Large", 1, 20.0),
            _entry("B", "L1b", "Large", 1, 21.0),
        ]),
        _run("Agility", "Large", 3, [
            _entry("C", "L3a", "Large", 3, 20.0),
            _entry("D", "L3b", "Large", 3, 21.0),
        ]),
    ]
    event = {"runs": runs}
    blocks = koq.ranking_tables(event)
    agi = next(b for b in blocks if b["label"] == "Agility")
    large = agi["tables"]["Large"]
    assert large["combined"] is False
    labels = sorted(sub["class_label"] for sub in large["subtables"])
    assert labels == ["1", "3"]


def test_ranking_tables_doppelquali_status_dup():
    tunnel = _run("Tunnellauf", "Large", "1-3", [
        _entry("STAR", "Star", "Large", 2, 25.0),
    ])
    agi = _run("Agility", "Large", 2, [
        _entry("STAR", "Star", "Large", 2, 20.0),
        _entry("B", "Second", "Large", 2, 21.0),
        _entry("C", "Third", "Large", 2, 22.0),
        _entry("D", "Fourth", "Large", 2, 23.0),
    ])
    event = {"runs": [tunnel, agi]}
    blocks = koq.ranking_tables(event)
    agi_block = next(b for b in blocks if b["label"] == "Agility")
    rows = agi_block["tables"]["Large"]["subtables"][0]["rows"]
    star_row = next(r for r in rows if r["dog_name"] == "Star")
    assert star_row["status"] == "dup"   # schon via Tunnellauf quali
    # die drei anderen rücken nach (3 Spots)
    quali = [r["dog_name"] for r in rows if r["status"] == "quali"]
    assert quali == ["Second", "Third", "Fourth"]
