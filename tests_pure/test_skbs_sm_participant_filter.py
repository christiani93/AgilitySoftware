"""
SM-Hund-Filter der SKBS-SM: nur gemeldete SM-Teilnehmer zählen.

Am selben Large-Event können Teilnehmer nur SM, nur FMBB-Quali, beides oder gar
keine Sonderwertung laufen. Der Per-Anmeldung-Marker entry["skbs_sm"] (vom Portal)
filtert Quote/Quali/Nachrücken. Die SM-only-SCT (Kl.2/3 feldabhängig) wird über
recalc_fn ausschliesslich über das SM-Feld neu gerechnet.
"""
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
WEB_APP_PATH = os.path.join(PROJECT_ROOT, "web_app")
if WEB_APP_PATH not in sys.path:
    sys.path.insert(0, WEB_APP_PATH)

from skbs_sm_qualification import calculate_skbs_sm_qualification  # noqa: E402


def _entry(license_no, rang, fehler_total=0, zeit_total=40.0, skbs_sm=None, zeit=None):
    e = {
        "Lizenznummer":    license_no,
        "Hundename":       f"Hund_{license_no}",
        "Vorname":         "Max",
        "Nachname":        f"M_{license_no}",
        "platz":           rang,
        "fehler_total":    fehler_total,
        "fehler_parcours": 0,
        "zeit_total":      zeit_total,
    }
    if skbs_sm is not None:
        e["skbs_sm"] = skbs_sm
    if zeit is not None:
        e["zeit"] = zeit
    return e


def _run(klasse, laufart, entries, is_final=False):
    return {
        "kategorie": "Large",
        "klasse":    klasse,
        "laufart":   laufart,
        "is_final":  is_final,
        "laufdaten": {"parcours_laenge": 180.0},
        "entries":   entries,
    }


def _kl3_event(entries_factory, config=None):
    """Kl.3 Agility+Jumping mit identischem Feld (per-Lauf frisch gebaut)."""
    event = {"runs": [
        _run("3", "Agility", entries_factory()),
        _run("3", "Jumping", entries_factory()),
    ]}
    if config is not None:
        event["skbs_sm_config"] = config
    return event


def test_per_entry_flag_excludes_non_sm():
    # Nicht-SM-Hund "99" ist bestplatziert (rang 1), aber skbs_sm=False → NICHT qualifiziert.
    def field():
        return [
            _entry("99", 1, skbs_sm=False),
            _entry("1", 2, skbs_sm=True),
            _entry("2", 3, skbs_sm=True),
            _entry("3", 4, skbs_sm=True),
        ]
    result = calculate_skbs_sm_qualification(_kl3_event(field))
    licenses = {f["license"] for f in result["finalists"]}
    assert "99" not in licenses
    assert {"1", "2", "3"} <= licenses


def test_no_flag_counts_all_backward_compat():
    # Ohne skbs_sm-Feld: kein Filter → ganzes Feld zählt (bisheriges Verhalten).
    def field():
        return [
            _entry("99", 1),
            _entry("1", 2),
            _entry("2", 3),
            _entry("3", 4),
        ]
    result = calculate_skbs_sm_qualification(_kl3_event(field))
    licenses = {f["license"] for f in result["finalists"]}
    assert "99" in licenses  # bestplatziert, zählt mangels Filter mit


def test_license_list_fallback_filters():
    # Keine Per-Entry-Flags, aber Lizenz-Liste in der Config → filtert.
    def field():
        return [
            _entry("99", 1),
            _entry("1", 2),
            _entry("2", 3),
            _entry("3", 4),
        ]
    result = calculate_skbs_sm_qualification(
        _kl3_event(field, config={"sm_licenses": ["1", "2", "3"]}))
    licenses = {f["license"] for f in result["finalists"]}
    assert "99" not in licenses
    assert {"1", "2", "3"} <= licenses


def test_recompute_runs_on_sm_only_field():
    # Mit Rohdaten (zeit) + recalc_fn: der Recompute sieht NUR das SM-Feld (3 Hunde),
    # nicht das Gesamtfeld (4) — so basiert die SCT auf dem schnellsten SM-Hund.
    seen_counts = []

    def recalc(run):
        seen_counts.append(len(run["entries"]))

    def field():
        return [
            _entry("99", 1, skbs_sm=False, zeit=30.0),
            _entry("1", 2, skbs_sm=True, zeit=35.0),
            _entry("2", 3, skbs_sm=True, zeit=40.0),
            _entry("3", 4, skbs_sm=True, zeit=45.0),
        ]
    calculate_skbs_sm_qualification(_kl3_event(field), recalc_fn=recalc)
    assert seen_counts, "recalc_fn wurde nie aufgerufen (Recompute-Pfad nicht aktiv)"
    assert all(c == 3 for c in seen_counts), (
        f"Recompute lief über das Gesamtfeld statt SM-only: {seen_counts}")
