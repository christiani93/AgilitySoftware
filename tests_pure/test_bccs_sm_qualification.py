"""
Pure-Python-Tests für den BCCS-SM-Qualifikations-Service.

Abgedeckte Regeln (Reglement BCCS 2023):
- Quote: 15 % aufgerundet, kein Minimum
- Kategorien Intermediate + Large getrennt
- Divisionen SM (Kl.3) vs. Nachwuchs (Kl.1+2 kombiniert)
- Doppelqualifikation → alternierendes Nachrücken zwischen den 2 Quali-Läufen
- Titelverteidiger pro Division (gestartet → gesetzt; nicht gestartet → nicht)
- DIS wird nicht qualifiziert
- Final: 2 Läufe summiert, 3-stufiger Tiebreaker + ex aequo
"""
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
WEB_APP_PATH = os.path.join(PROJECT_ROOT, "web_app")
if WEB_APP_PATH not in sys.path:
    sys.path.insert(0, WEB_APP_PATH)

from bccs_sm_qualification import (   # noqa: E402
    calculate_bccs_sm_qualification,
    rank_final_bccs,
    final_run2_start_order,
    apply_final_start_order,
    _quota,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _entry(lic, fehler_total=0, fehler_parcours=0, zeit_total=40.0, platz=None, dis=None):
    e = {
        "Lizenznummer":    lic,
        "Hundename":       f"Hund_{lic}",
        "Vorname":         "Max",
        "Nachname":        f"M_{lic}",
        "platz":           platz,
        "fehler_total":    fehler_total,
        "fehler_parcours": fehler_parcours,
        "zeit_total":      zeit_total,
    }
    if dis:
        e["disqualifikation"] = dis
        e["fehler_total"] = 999
        e["platz"] = None
    return e


def _run(kategorie, klasse, laufart, entries, is_final=False):
    return {
        "kategorie": kategorie,
        "klasse":    klasse,
        "laufart":   laufart,
        "is_final":  is_final,
        "entries":   entries,
    }


def _seq(prefix, n, start=0):
    """n Einträge mit aufsteigenden Fehlern (deterministische Leistungsreihenfolge)."""
    return [_entry(f"{prefix}{i}", fehler_total=start + i, zeit_total=30.0 + i) for i in range(n)]


def _licenses(div_result):
    return [f["license"] for f in div_result["finalists"]]


# ---------------------------------------------------------------------------
# Quote
# ---------------------------------------------------------------------------

def test_quota_15_prozent_aufgerundet_kein_minimum():
    assert _quota(0) == 0
    assert _quota(1) == 1      # ceil(0.15)
    assert _quota(6) == 1      # ceil(0.9)
    assert _quota(7) == 2      # ceil(1.05)
    assert _quota(20) == 3     # ceil(3.0)
    assert _quota(21) == 4     # ceil(3.15)
    assert _quota(100) == 15


# ---------------------------------------------------------------------------
# Kategorien + Divisionen getrennt, keine Doppelqualifikation
# ---------------------------------------------------------------------------

def test_intermediate_und_large_sm_getrennt():
    """7 Starter/Lauf → Quote 2; I und L dürfen sich nicht vermischen."""
    event = {"runs": [
        _run("Large", "3", "Agility",  _seq("L", 7)),
        _run("Large", "3", "Jumping",  _seq("M", 7)),
        _run("Intermediate", "3", "Agility", _seq("I", 7)),
        _run("Intermediate", "3", "Jumping", _seq("J", 7)),
    ]}
    res = calculate_bccs_sm_qualification(event)

    large = res["divisions"]["Large/sm"]
    inter = res["divisions"]["Intermediate/sm"]
    assert large["quota"] == {"Agility": 2, "Jumping": 2}
    # Top 2 je Lauf, keine Überschneidung → 4 Finalisten je Kategorie
    assert set(_licenses(large)) == {"L0", "L1", "M0", "M1"}
    assert set(_licenses(inter)) == {"I0", "I1", "J0", "J1"}
    assert large["open_spots"] == 0 and inter["open_spots"] == 0


def test_sm_klasse3_und_nachwuchs_klasse12_getrennt():
    """Klasse-3-Hunde landen in SM, Klasse-1/2-Hunde in Nachwuchs."""
    event = {"runs": [
        _run("Large", "3", "Agility", _seq("SM", 7)),
        _run("Large", "1", "Agility", _seq("NW", 7)),
    ]}
    res = calculate_bccs_sm_qualification(event)
    assert set(_licenses(res["divisions"]["Large/sm"])) == {"SM0", "SM1"}
    assert set(_licenses(res["divisions"]["Large/nachwuchs"])) == {"NW0", "NW1"}


# ---------------------------------------------------------------------------
# Doppelqualifikation + alternierendes Nachrücken
# ---------------------------------------------------------------------------

def test_doppelqualifikation_alternierendes_nachruecken():
    """Top-2 beider Läufe identisch (A,B) → 2 Lücken; Nachrücker alternierend Agi→Jump."""
    agility = [_entry("A", 0), _entry("B", 1), _entry("C", 2), _entry("D", 3),
               _entry("E", 4), _entry("F", 5), _entry("G", 6)]              # 7 → Quote 2
    jumping = [_entry("A", 0), _entry("B", 1), _entry("X", 2), _entry("Y", 3),
               _entry("Z", 4), _entry("W", 5), _entry("V", 6)]              # 7 → Quote 2
    event = {"runs": [
        _run("Large", "3", "Agility", agility),
        _run("Large", "3", "Jumping", jumping),
    ]}
    res = calculate_bccs_sm_qualification(event)
    large = res["divisions"]["Large/sm"]
    lics = _licenses(large)

    # A nur einmal (Doppelqualifikation)
    assert lics.count("A") == 1
    # Direkt: A, B (aus Agility)
    direct = [f for f in large["finalists"] if f["source"] in ("agility", "jumping")]
    assert {f["license"] for f in direct} == {"A", "B"}
    # Nachrücker alternierend: zuerst C (Agility), dann X (Jumping)
    nach = [f for f in large["finalists"] if f["source"] == "nachruecker"]
    assert [f["license"] for f in nach] == ["C", "X"]
    assert large["open_spots"] == 0
    # Maximalzahl respektiert (Quote-Summe = 4)
    assert len(lics) == 4


def test_nachruecken_endet_wenn_keine_kandidaten():
    """Beide Läufe komplett doppelqualifiziert, zu wenig Kandidaten → open_spots > 0."""
    # Nur 7 Starter, aber Top-2 in beiden gleich und sonst niemand platziert
    agility = [_entry("A", 0), _entry("B", 1)] + [_entry(f"d{i}", dis="DIS") for i in range(5)]
    jumping = [_entry("A", 0), _entry("B", 1)] + [_entry(f"e{i}", dis="DIS") for i in range(5)]
    event = {"runs": [
        _run("Large", "3", "Agility", agility),
        _run("Large", "3", "Jumping", jumping),
    ]}
    res = calculate_bccs_sm_qualification(event)
    large = res["divisions"]["Large/sm"]
    assert set(_licenses(large)) == {"A", "B"}
    # Quote 2+2 = 4, nur 2 platziert (A,B) → 2 offen
    assert large["open_spots"] == 2


# ---------------------------------------------------------------------------
# Nachwuchs: Klassen 1+2 kombiniert nach Leistung
# ---------------------------------------------------------------------------

def test_nachwuchs_klasse_1_und_2_separat_gewertet():
    """Kl.1 und Kl.2 werden GETRENNT gewertet — je eigene 15 %-Quote.
    Unterscheidet sich von 'kombiniert': der schwache Kl.2-Hund (10 FP) qualifiziert
    sich als Klassenbester, obwohl er im kombinierten Pool rausfiele."""
    klasse1 = [_entry(f"A{i}", i) for i in range(7)]                  # 7 → Quote 2 → A0, A1
    klasse2 = [_entry("B0", 10), _entry("B1", 11), _entry("B2", 12)]  # 3 → Quote 1 → B0
    event = {"runs": [
        _run("Intermediate", "1", "Agility", klasse1),
        _run("Intermediate", "2", "Agility", klasse2),
    ]}
    nw = calculate_bccs_sm_qualification(event)["divisions"]["Intermediate/nachwuchs"]
    quali = {f["license"]: f for f in nw["finalists"] if f["source"] == "agility"}
    assert set(quali) == {"A0", "A1", "B0"}          # 2 aus Kl.1 + 1 aus Kl.2 (getrennt)
    assert quali["A0"]["from_class"] == 1 and quali["B0"]["from_class"] == 2
    assert nw["quota"]["Agility"] == 3               # Quote-Summe Division = 2 (Kl1) + 1 (Kl2)


# ---------------------------------------------------------------------------
# Titelverteidiger
# ---------------------------------------------------------------------------

def test_titelverteidiger_gesetzt_wenn_gestartet():
    event = {
        "runs": [
            _run("Large", "3", "Agility", [
                _entry("A", 0), _entry("B", 1), _entry("CHAMP", 50),  # CHAMP schlecht
            ]),
        ],
        "bccs_sm_config": {
            "defending_champions": [
                {"license": "CHAMP", "dog_name": "Vorjahr", "handler_name": "HF",
                 "category": "Large", "division": "sm"},
            ],
        },
    }
    res = calculate_bccs_sm_qualification(event)
    large = res["divisions"]["Large/sm"]
    champ = [f for f in large["finalists"] if f["license"] == "CHAMP"]
    assert len(champ) == 1 and champ[0]["source"] == "title_defender"
    # Nicht in anderer Division
    assert "CHAMP" not in _licenses(res["divisions"]["Intermediate/sm"])


def test_titelverteidiger_nicht_gestartet_nicht_gesetzt():
    event = {
        "runs": [_run("Large", "3", "Agility", [_entry("A", 0)])],
        "bccs_sm_config": {
            "defending_champions": [
                {"license": "ABSENT", "category": "Large", "division": "sm"},
            ],
        },
    }
    res = calculate_bccs_sm_qualification(event)
    assert "ABSENT" not in _licenses(res["divisions"]["Large/sm"])


# ---------------------------------------------------------------------------
# DIS
# ---------------------------------------------------------------------------

def test_dis_wird_nicht_qualifiziert():
    event = {"runs": [
        _run("Large", "3", "Agility", [
            _entry("A", 0),
            _entry("DIS_DOG", dis="DIS"),
        ]),
    ]}
    res = calculate_bccs_sm_qualification(event)
    lics = _licenses(res["divisions"]["Large/sm"])
    assert "A" in lics and "DIS_DOG" not in lics


# ---------------------------------------------------------------------------
# Final: 2 Läufe summiert
# ---------------------------------------------------------------------------

def test_final_zwei_laeufe_summiert_tiebreaker():
    event = {"runs": [
        _run("Large", "3", "Jumping", [
            _entry("P", fehler_total=0, fehler_parcours=0, zeit_total=30.0),
            _entry("Q", fehler_total=0, fehler_parcours=0, zeit_total=31.0),
            _entry("R", fehler_total=5, fehler_parcours=5, zeit_total=30.0),
        ], is_final=True),
        _run("Large", "3", "Agility", [
            _entry("P", fehler_total=0, fehler_parcours=0, zeit_total=30.0),
            _entry("Q", fehler_total=0, fehler_parcours=0, zeit_total=30.0),
            _entry("R", fehler_total=0, fehler_parcours=0, zeit_total=30.0),
        ], is_final=True),
    ]}
    final = rank_final_bccs(event)["Large/sm"]
    order = [d["license"] for d in final]
    # P: 0 FP, 60s; Q: 0 FP, 61s; R: 5 FP → P, Q, R
    assert order == ["P", "Q", "R"]
    assert [d["final_rang"] for d in final] == [1, 2, 3]


def test_final_ex_aequo():
    event = {"runs": [
        _run("Large", "3", "Jumping", [
            _entry("P", fehler_total=5, fehler_parcours=5, zeit_total=30.0),
            _entry("Q", fehler_total=5, fehler_parcours=5, zeit_total=30.0),
            _entry("R", fehler_total=10, fehler_parcours=10, zeit_total=35.0),
        ], is_final=True),
        _run("Large", "3", "Agility", [
            _entry("P", fehler_total=0, fehler_parcours=0, zeit_total=30.0),
            _entry("Q", fehler_total=0, fehler_parcours=0, zeit_total=30.0),
            _entry("R", fehler_total=0, fehler_parcours=0, zeit_total=30.0),
        ], is_final=True),
    ]}
    final = rank_final_bccs(event)["Large/sm"]
    rang = {d["license"]: d["final_rang"] for d in final}
    assert rang["P"] == 1 and rang["Q"] == 1 and rang["R"] == 3


def test_final_nur_ein_lauf_kein_rang():
    """Team mit nur einem der beiden Finalläufe wird ohne Rang ans Ende gesetzt."""
    event = {"runs": [
        _run("Large", "3", "Jumping", [
            _entry("P", fehler_total=0, zeit_total=30.0),
            _entry("ONLYJUMP", fehler_total=0, zeit_total=30.0),
        ], is_final=True),
        _run("Large", "3", "Agility", [
            _entry("P", fehler_total=0, zeit_total=30.0),
        ], is_final=True),
    ]}
    final = rank_final_bccs(event)["Large/sm"]
    rang = {d["license"]: d["final_rang"] for d in final}
    assert rang["P"] == 1
    assert rang["ONLYJUMP"] is None


def test_final_dis_nicht_klassiert_hinter_sauberen():
    """DIS-Teams sind nicht klassiert (kein Rang, keine gültige Kombination), werden
    aber weiterhin gelistet — hinter allen in beiden Läufen sauberen Teams, stabil
    nach Lizenz (egal in welchem Lauf die DIS passierte)."""
    event = {"runs": [
        _run("Large", "3", "Jumping", [
            _entry("CLEAN",  fehler_total=0, fehler_parcours=0, zeit_total=30.0),
            _entry("CLEAN2", fehler_total=5, fehler_parcours=5, zeit_total=30.0),
            _entry("ADIS",   fehler_total=0, fehler_parcours=0, zeit_total=28.0),  # Jump sauber
            _entry("JDIS",   dis="DIS"),
            _entry("BOTH",   dis="DIS"),
        ], is_final=True),
        _run("Large", "3", "Agility", [
            _entry("CLEAN",  fehler_total=0, fehler_parcours=0, zeit_total=35.0),
            _entry("CLEAN2", fehler_total=0, fehler_parcours=0, zeit_total=35.0),
            _entry("ADIS",   dis="DIS"),
            _entry("JDIS",   fehler_total=0, fehler_parcours=0, zeit_total=40.0),  # Agi sauber
            _entry("BOTH",   dis="DIS"),
        ], is_final=True),
    ]}
    final = rank_final_bccs(event)["Large/sm"]
    order = [d["license"] for d in final]
    rang = {d["license"]: d["final_rang"] for d in final}
    # Nur die in beiden Läufen sauberen Teams sind klassiert.
    assert order[:2] == ["CLEAN", "CLEAN2"]
    assert rang["CLEAN"] == 1 and rang["CLEAN2"] == 2
    # Alle DIS-Teams: unrangiert, dahinter, stabil nach Lizenz (ADIS < BOTH < JDIS).
    assert order[2:] == ["ADIS", "BOTH", "JDIS"]
    assert all(rang[l] is None for l in ("ADIS", "JDIS", "BOTH"))


def test_final_run2_start_order_reverse_mit_dis_zuerst():
    """2. Finallauf (Agility) = umgekehrte Rangliste des 1. Laufs (Jumping):
    DIS/nicht klassiert zuerst (nach Startnummer), dann Schlechtester→Sieger."""
    run1 = [
        {"Lizenznummer": "A", "platz": 1, "Startnummer": 3},
        {"Lizenznummer": "B", "platz": 2, "Startnummer": 1},
        {"Lizenznummer": "C", "platz": 3, "Startnummer": 4},
        {"Lizenznummer": "D", "platz": None, "Startnummer": 5},  # DIS
        {"Lizenznummer": "E", "platz": None, "Startnummer": 2},  # DIS
    ]
    order = final_run2_start_order(run1)
    # DIS zuerst nach Startnummer (E=2, D=5), dann klassiert umgekehrt (C, B, A).
    assert order == ["E", "D", "C", "B", "A"]


def test_apply_final_start_order_schreibt_start_order_auf_agility():
    """apply_final_start_order paart Jumping→Agility-Final je (Kat,Kl) und schreibt
    die umgekehrte Reihenfolge als start_order auf die Agility-Entries."""
    jump_entries = [
        {"Lizenznummer": "A", "platz": 1, "Startnummer": 3},
        {"Lizenznummer": "B", "platz": 2, "Startnummer": 1},
        {"Lizenznummer": "C", "platz": 3, "Startnummer": 4},
        {"Lizenznummer": "D", "platz": None, "Startnummer": 5},  # DIS
        {"Lizenznummer": "E", "platz": None, "Startnummer": 2},  # DIS
    ]
    agi_entries = [{"Lizenznummer": lic} for lic in ("A", "B", "C", "D", "E")]
    event = {"runs": [
        {"kategorie": "Large", "klasse": "3", "laufart": "Jumping", "is_final": True, "entries": jump_entries},
        {"kategorie": "Large", "klasse": "3", "laufart": "Agility", "is_final": True, "entries": agi_entries},
    ]}
    applied = apply_final_start_order(event, lambda run: run["entries"])
    assert applied == [{"kategorie": "Large", "klasse": "3", "count": 5}]
    so = {e["Lizenznummer"]: e["start_order"] for e in agi_entries}
    # E(DIS,Startnr2)=1, D(DIS,Startnr5)=2, dann C,B,A (umgekehrte Rangfolge)
    assert so == {"E": 1, "D": 2, "C": 3, "B": 4, "A": 5}


# ---------------------------------------------------------------------------
# SM-Hund-Filter (Reglement P.2): offenes Turnier, nur markierte Border zählen
# ---------------------------------------------------------------------------

def _sm(e):
    """Markiert ein Entry als SM-Teilnehmer (Checkbox/AOA-Flag)."""
    e["bccs_sm"] = True
    return e


def test_per_entry_flag_nur_sm_hunde_zaehlen():
    """Gemischtes offenes Feld: 10 Nicht-SM (BESTE Leistung, unmarkiert) + 10 SM-Hunde.
    Quote muss auf den 10 SM-Startern basieren (nicht 20); nur SM-Hunde werden Finalisten."""
    non_sm = [_entry(f"X{i}", fehler_total=i) for i in range(10)]           # beste Zeiten, KEIN Flag
    sm     = [_sm(_entry(f"S{i}", fehler_total=10 + i)) for i in range(10)]
    pool = non_sm + sm
    event = {"runs": [
        _run("Large", "3", "Agility", [dict(e) for e in pool]),
        _run("Large", "3", "Jumping", [dict(e) for e in pool]),
    ]}
    large = calculate_bccs_sm_qualification(event)["divisions"]["Large/sm"]
    assert large["quota"] == {"Agility": 2, "Jumping": 2}     # 15 % von 10, nicht von 20
    licenses = set(_licenses(large))
    assert licenses == {"S0", "S1", "S2", "S3"}               # Doppelquali → Nachrücken
    assert all(l.startswith("S") for l in licenses)           # kein Nicht-SM-Hund dabei


def test_lizenzliste_fallback_ohne_per_entry_flag():
    """Ohne Per-Entry-Flag greift bccs_sm_config.sm_licenses als Filterquelle."""
    non_sm = [_entry(f"X{i}", fehler_total=i) for i in range(10)]
    sm     = [_entry(f"S{i}", fehler_total=10 + i) for i in range(10)]      # KEIN Flag
    pool = non_sm + sm
    event = {
        "bccs_sm_config": {"sm_licenses": [f"S{i}" for i in range(10)]},
        "runs": [
            _run("Large", "3", "Agility", [dict(e) for e in pool]),
            _run("Large", "3", "Jumping", [dict(e) for e in pool]),
        ],
    }
    large = calculate_bccs_sm_qualification(event)["divisions"]["Large/sm"]
    assert large["quota"] == {"Agility": 2, "Jumping": 2}
    assert set(_licenses(large)) == {"S0", "S1", "S2", "S3"}


def test_ohne_markierung_zaehlen_alle_abwaertskompatibel():
    """Kein bccs_sm-Feld + keine sm_licenses → kein Filter (alle 20 zählen → Quote 3)."""
    pool = [_entry(f"A{i}", fehler_total=i) for i in range(20)]
    event = {"runs": [
        _run("Large", "3", "Agility", [dict(e) for e in pool]),
        _run("Large", "3", "Jumping", [dict(e) for e in pool]),
    ]}
    large = calculate_bccs_sm_qualification(event)["divisions"]["Large/sm"]
    assert large["quota"] == {"Agility": 3, "Jumping": 3}


def test_final_filtert_nicht_sm_hunde():
    """Auch die Final-Rangierung zählt nur markierte SM-Hunde — der schnellere Nicht-SM fällt raus."""
    agi = [_sm(_entry("S", fehler_total=0, zeit_total=30.0)),
           _entry("X", fehler_total=0, zeit_total=20.0)]                    # schneller, aber nicht SM
    jmp = [_sm(_entry("S", fehler_total=0, zeit_total=30.0)),
           _entry("X", fehler_total=0, zeit_total=20.0)]
    event = {"runs": [
        _run("Large", "3", "Jumping", [dict(e) for e in jmp], is_final=True),
        _run("Large", "3", "Agility", [dict(e) for e in agi], is_final=True),
    ]}
    final = rank_final_bccs(event)["Large/sm"]
    licenses = {d["license"] for d in final}
    assert "X" not in licenses
    assert any(d["license"] == "S" and d["final_rang"] == 1 for d in final)
