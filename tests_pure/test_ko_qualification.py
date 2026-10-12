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
# apply_single_run_qualification: schrittweise, pro Lauf anhängen
# ---------------------------------------------------------------------------

def _two_run_event():
    """Event mit Tunnellauf (kombiniert, Large 2 Plätze) + Agility (split, Kl1
    1 Platz). Alpha ist Doppelqualifikant (Tunnel + Agility Kl1)."""
    tunnel = _run("Tunnellauf", "Large", "1-3", [
        _entry("L1", "Alpha", "Large", 1, 20.0),   # schnellster -> Tunnel-Quali
        _entry("L2", "Bravo", "Large", 2, 21.0),   # 2. -> Tunnel-Quali
        _entry("L3", "Charlie", "Large", 3, 22.0),
    ])
    agility = _run("Agility", "Large", 1, [
        _entry("L1", "Alpha", "Large", 1, 19.0),   # schon via Tunnel -> rückt nach
        _entry("L4", "Delta", "Large", 1, 25.0),   # nächster -> Agility-Quali
    ])
    schluessel = {"runs": [
        {"label": "Tunnellauf", "match": {"laufart": "Tunnellauf"},
         "split_by_class": False, "spots": {"Large": 2}},
        {"label": "Agility", "match": {"laufart": "Agility"},
         "split_by_class": True, "spots": {"Large": 1}},
    ]}
    event = {"runs": [tunnel, agility]}
    return event, schluessel


def test_single_run_haengt_an_und_erhaelt_losnummern():
    event, schluessel = _two_run_event()

    # Lauf 0 (Tunnellauf) ableiten -> Alpha, Bravo
    r0 = koq.apply_single_run_qualification(event, 0, schluessel)
    assert r0["run_label"] == "Tunnellauf"
    large = next(f for f in event["ko_cup"]["finals"] if f["category_code"] == "Large")
    assert set(_names(large["participants"])) == {"Alpha", "Bravo"}

    # Losnummern simulieren (an der Rangverkündigung vergeben)
    for p, n in zip(large["participants"], (1, 2)):
        p["draw_number"] = n

    # Lauf 1 (Agility) ableiten -> Alpha schon quali -> Delta rückt nach, ANGEHÄNGT
    r1 = koq.apply_single_run_qualification(event, 1, schluessel)
    assert r1["counts"]["Large"]["derived"] == 1
    large = next(f for f in event["ko_cup"]["finals"] if f["category_code"] == "Large")
    assert set(_names(large["participants"])) == {"Alpha", "Bravo", "Delta"}
    # bestehende Losnummern unverändert, Delta noch ohne
    by_name = {p["dog_name"]: p for p in large["participants"]}
    assert by_name["Alpha"]["draw_number"] == 1
    assert by_name["Bravo"]["draw_number"] == 2
    assert by_name["Delta"]["draw_number"] is None
    # Bracket invalidiert
    assert large["matchups"] == [] and large["results"] == []


def test_single_run_ist_idempotent():
    event, schluessel = _two_run_event()
    koq.apply_single_run_qualification(event, 0, schluessel)
    koq.apply_single_run_qualification(event, 1, schluessel)
    large = next(f for f in event["ko_cup"]["finals"] if f["category_code"] == "Large")
    before = sorted(_names(large["participants"]))

    # Tunnellauf ERNEUT ableiten -> darf NICHT via Nachrücken Charlie hinzufügen
    koq.apply_single_run_qualification(event, 0, schluessel)
    large = next(f for f in event["ko_cup"]["finals"] if f["category_code"] == "Large")
    assert sorted(_names(large["participants"])) == before
    tun = [p for p in large["participants"] if p.get("quali_label") == "Tunnellauf"]
    assert set(_names(tun)) == {"Alpha", "Bravo"}


def test_single_run_erhaelt_manuelle_und_andere_laeufe():
    event, schluessel = _two_run_event()
    # manueller Titelverteidiger vorweg
    event["ko_cup"] = {"enabled": True, "finals": [{
        "id": "fL", "category_code": "Large", "group_label": "Large",
        "participants": [{"id": "pc", "dog_name": "Champ", "license_no": "CH",
                          "source": "title_defender", "draw_number": 1}],
        "matchups": [], "results": [], "is_published": False,
    }]}
    koq.apply_single_run_qualification(event, 0, schluessel)
    large = next(f for f in event["ko_cup"]["finals"] if f["category_code"] == "Large")
    # Champ (manuell, mit Losnr) bleibt, Tunnel-Finalisten dazu
    by_name = {p["dog_name"]: p for p in large["participants"]}
    assert "Champ" in by_name and by_name["Champ"]["draw_number"] == 1
    assert "Alpha" in by_name and "Bravo" in by_name


def test_single_run_ungueltiger_index():
    event, schluessel = _two_run_event()
    try:
        koq.apply_single_run_qualification(event, 9, schluessel)
    except IndexError:
        pass
    else:
        raise AssertionError("IndexError erwartet")


def _split_class_event():
    """Agility (split_by_class, Large 1 Platz/Klasse) mit Kl1 + Kl2."""
    agility_k1 = _run("Agility", "Large", 1, [
        _entry("L1", "Uno", "Large", 1, 20.0),
        _entry("L2", "Dos", "Large", 1, 21.0),
    ])
    agility_k2 = _run("Agility", "Large", 2, [
        _entry("L3", "Tres", "Large", 2, 20.0),
        _entry("L4", "Quatro", "Large", 2, 21.0),
    ])
    schluessel = {"runs": [
        {"label": "Agility", "match": {"laufart": "Agility"},
         "split_by_class": True, "spots": {"Large": 1}},
    ]}
    event = {"runs": [agility_k1, agility_k2]}
    return event, schluessel


def test_single_run_pro_klasse_leitet_nur_eine_klasse_ab():
    event, schluessel = _split_class_event()

    # Nur Kl.1 ableiten -> nur Uno (Kl1-Sieger), KEIN Kl2-Finalist.
    r1 = koq.apply_single_run_qualification(event, 0, schluessel, class_filter="1")
    assert r1["class_label"] == "1"
    large = next(f for f in event["ko_cup"]["finals"] if f["category_code"] == "Large")
    assert _names(large["participants"]) == ["Uno"]
    assert large["participants"][0]["from_class"] == 1
    large["participants"][0]["draw_number"] = 5   # Losnummer vergeben

    # Jetzt Kl.2 ableiten -> Tres ANGEHÄNGT, Uno + Losnummer bleiben.
    r2 = koq.apply_single_run_qualification(event, 0, schluessel, class_filter="2")
    assert r2["class_label"] == "2"
    large = next(f for f in event["ko_cup"]["finals"] if f["category_code"] == "Large")
    by_name = {p["dog_name"]: p for p in large["participants"]}
    assert set(by_name) == {"Uno", "Tres"}
    assert by_name["Uno"]["draw_number"] == 5
    assert by_name["Tres"]["from_class"] == 2


def test_single_run_pro_klasse_idempotent_laesst_andere_klasse_in_ruhe():
    event, schluessel = _split_class_event()
    koq.apply_single_run_qualification(event, 0, schluessel, class_filter="1")
    koq.apply_single_run_qualification(event, 0, schluessel, class_filter="2")
    large = next(f for f in event["ko_cup"]["finals"] if f["category_code"] == "Large")
    for p in large["participants"]:
        p["draw_number"] = {"Uno": 1, "Tres": 2}[p["dog_name"]]

    # Kl.1 ERNEUT ableiten -> Uno unverändert, Tres (Kl2) + dessen Losnummer bleiben.
    koq.apply_single_run_qualification(event, 0, schluessel, class_filter="1")
    large = next(f for f in event["ko_cup"]["finals"] if f["category_code"] == "Large")
    by_name = {p["dog_name"]: p for p in large["participants"]}
    assert set(by_name) == {"Uno", "Tres"}
    assert by_name["Tres"]["draw_number"] == 2


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


# ---------------------------------------------------------------------------
# Quell-Event pro Schlüssel-Lauf (Mehrtages-Event online getrennt importiert)
# ---------------------------------------------------------------------------

def test_source_event_id_zieht_laeufe_aus_fremdem_event():
    # Der Freitag-Tunnellauf liegt als EIGENES Event vor (online getrennt),
    # das Sa-Event hat selbst keinen Tunnellauf. Mit source_event_id soll die
    # Ableitung die Tunnellauf-Finalisten trotzdem aus dem Fr-Event ziehen.
    friday = {
        "id": "ev_friday",
        "runs": [_run("Tunnellauf", "Large", "1-3", [
            _entry("L1", "Alpha", "Large", 1, 30.0),
            _entry("L2", "Bravo", "Large", 2, 28.0),
            _entry("L3", "Charlie", "Large", 3, 26.0),
        ])],
    }
    saturday = {"id": "ev_saturday", "runs": []}   # eigener Tunnellauf fehlt
    schluessel = {"runs": [{
        "label": "Tunnellauf", "match": {"laufart": "Tunnellauf"},
        "split_by_class": False,
        "spots": {"Large": 3, "Intermediate": 0, "Medium": 0, "Small": 0},
        "source_event_id": "ev_friday",
    }]}
    source_lookup = {"ev_friday": friday, "ev_saturday": saturday}

    # Ohne source_lookup: nichts (Sa-Event hat keine Läufe)
    res_bare = koq.calculate_ko_qualification(saturday, schluessel)
    assert res_bare["derived"]["Large"] == []

    # Mit source_lookup: die 3 schnellsten aus dem Fr-Event
    res = koq.calculate_ko_qualification(saturday, schluessel, source_lookup=source_lookup)
    assert _names(res["derived"]["Large"]) == ["Charlie", "Bravo", "Alpha"]


def test_source_event_id_leer_nimmt_eigenes_event():
    # Leeres/fehlendes source_event_id → Läufe DIESES Events (Offline-Fall).
    own = {
        "id": "ev_own",
        "runs": [_run("Tunnellauf", "Large", "1-3", [
            _entry("X1", "Own1", "Large", 1, 20.0),
            _entry("X2", "Own2", "Large", 2, 21.0),
        ])],
    }
    other = {"id": "ev_other", "runs": [_run("Tunnellauf", "Large", "1-3", [
        _entry("Y1", "Other1", "Large", 1, 10.0),
    ])]}
    schluessel = {"runs": [{
        "label": "Tunnellauf", "match": {"laufart": "Tunnellauf"},
        "split_by_class": False,
        "spots": {"Large": 2, "Intermediate": 0, "Medium": 0, "Small": 0},
        "source_event_id": None,
    }]}
    res = koq.calculate_ko_qualification(
        own, schluessel, source_lookup={"ev_own": own, "ev_other": other})
    assert _names(res["derived"]["Large"]) == ["Own1", "Own2"]
