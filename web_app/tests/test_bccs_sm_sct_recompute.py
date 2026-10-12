"""
Regressionstest für den BCCS-SM-SCT-Neuberechnungs-Fix.

Hintergrund (Reglement BCCS P.2 + Standardzeit-Weisung): Das BCCS-SM läuft als offenes
Turnier; aus denselben Läufen entstehen ZWEI Ranglisten — (a) die offene (ganzes Feld)
und (b) die BCCS-only (nur SM-Hunde) pro Klasse/Kategorie. Für Klasse 2/3 wird die
Standardzeit (SCT) dynamisch aus der schnellsten *berücksichtigten* Zeit abgeleitet
(utils._calculate_run_results, Faktor Kl.3=1.3). Ist der schnellste Hund KEIN SM-Hund,
drückt er die offene SCT — die BCCS-only-Rangliste muss ihre Zeitfehler darum NEU über
das SM-Feld rechnen, sonst übernimmt sie die (zu strengen) Werte aus der offenen Wertung
und qualifiziert u.U. den falschen Hund.

Dieser Test braucht die echte utils.recalc_and_store (deshalb web_app/tests, flask_env),
nicht die pure-Python-Suite.
"""
from functools import partial

from utils import recalc_and_store
from bccs_sm_qualification import calculate_bccs_sm_qualification


def _entry(lic, zeit, fehler, bccs_sm):
    return {
        "Lizenznummer": lic,
        "Startnummer":  lic,
        "Hundename":    f"Hund_{lic}",
        "zeit":         f"{zeit:.2f}",
        "fehler":       str(fehler),
        "verweigerungen": "0",
        "dis_abr":      "",
        "bccs_sm":      bccs_sm,
    }


def _build_event():
    """Large, Klasse 3, Agility-Qualilauf mit einem schnellen Nicht-SM-Hund (N) und
    zwei SM-Hunden (A, B). Quote = ceil(2*0.15) = 1 → genau 1 Finalist.

    Offenes Feld:  schnellster = N (20.0) → SCT ceil(20*1.3)=26
        A (1 Parcoursfehler, 25.0): 5 + max(0,25-26)=0  = 5
        B (0 Parcoursfehler, 45.0): 0 + max(0,45-26)=19 = 19   → A vor B → Finalist (falsch) A
    SM-Feld:       schnellster SM = B (0 Fehler, 45.0) → SCT ceil(45*1.3)=59
        A: 5 + max(0,25-59)=0 = 5
        B: 0 + max(0,45-59)=0 = 0                              → B vor A → Finalist (korrekt) B
    """
    run = {
        "kategorie": "Large",
        "klasse":    "3",
        "laufart":   "Agility",
        "is_final":  False,
        "laufdaten": {},
        "entries": [
            _entry("N", 20.0, 0, bccs_sm=False),
            _entry("A", 25.0, 1, bccs_sm=True),
            _entry("B", 45.0, 0, bccs_sm=True),
        ],
    }
    return {"runs": [run]}, run


def test_sm_only_ranking_recomputes_sct_from_sm_field():
    event, run = _build_event()

    # Simuliert den Produktivablauf: die Läufe werden zuerst übers GANZE Feld gerechnet
    # (so wie routes_bccs_sm._recalc es tut) → Entries tragen jetzt die offenen Werte.
    recalc_and_store(run, {})

    # Ohne recalc_fn: Fallback liest die offenen (Gesamtfeld-)Werte → falscher Finalist A.
    buggy = calculate_bccs_sm_qualification(event)
    buggy_finalists = [f["license"] for f in buggy["divisions"]["Large/sm"]["finalists"]]
    assert buggy_finalists == ["A"], f"Fallback sollte die offene Wertung spiegeln, war {buggy_finalists}"

    # Mit recalc_fn: SCT wird aus dem SM-Feld neu gerechnet → regelkonformer Finalist B.
    recalc_fn = partial(recalc_and_store, settings={})
    fixed = calculate_bccs_sm_qualification(event, recalc_fn=recalc_fn)
    fixed_finalists = [f["license"] for f in fixed["divisions"]["Large/sm"]["finalists"]]
    assert fixed_finalists == ["B"], f"SM-Feld-SCT sollte B qualifizieren, war {fixed_finalists}"


def test_recompute_does_not_mutate_open_field_entries():
    """Die SM-Neuberechnung darf die Original-Entries (= offene Rangliste) NICHT verändern."""
    event, run = _build_event()
    recalc_and_store(run, {})

    open_values = {e["Lizenznummer"]: (e["fehler_total"], e["zeit_total"]) for e in run["entries"]}

    recalc_fn = partial(recalc_and_store, settings={})
    calculate_bccs_sm_qualification(event, recalc_fn=recalc_fn)

    after = {e["Lizenznummer"]: (e["fehler_total"], e["zeit_total"]) for e in run["entries"]}
    assert after == open_values, "Original-Entries wurden durch den SM-Recompute verändert"
