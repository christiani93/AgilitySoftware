"""Tests für die BCCS-SM-Quali-Rangliste im Ring-Monitor
(`_render_bccs_quali_ranking_section` via `routes_live.py`):

Zeigt die volle Quali-Rangliste des aktuellen Laufs (Top 4 + Quote) unter
"Aktueller Starter" — Analogon zur Final-Kombirangliste
(test_bccs_monitor_combined.py), aber während der Qualifikation.

Braucht App-/Babel-Kontext (gettext) → web_app/tests (flask_env).
"""
import blueprints.routes_live as rl


def _entry(lic, vorname, dog, fehler_total, fehler_parcours, zeit_total, dis=""):
    return {
        "Lizenznummer":    lic,
        "Startnummer":     lic,
        "Vorname":         vorname,
        "Nachname":        "Test",
        "Hundename":       dog,
        "fehler_total":    fehler_total,
        "fehler_parcours": fehler_parcours,
        "zeit_total":      zeit_total,
        "disqualifikation": dis,
        "platz":           None,
        "bccs_sm":         True,
    }


def _event(agi_entries, jump_entries):
    return {
        "Veranstaltungsart": "BCCS-SM",
        "runs": [
            {"kategorie": "Large", "klasse": "3", "laufart": "Agility",
             "is_final": False, "entries": agi_entries},
            {"kategorie": "Large", "klasse": "3", "laufart": "Jumping",
             "is_final": False, "entries": jump_entries},
        ],
    }


def _view(laufart="Agility", is_final=False):
    return {
        "current_run": {"kategorie": "Large", "klasse": "3",
                        "laufart": laufart, "is_final": is_final},
        "current_starter": {},
    }


def test_quali_ranking_rendered_with_quota_and_qualified_highlighted(app):
    # 7 Starter → Quote 2 (ceil(15%)). Top 2 (H0, H1) qualifizieren direkt.
    agi_entries = [_entry(str(100 + i), f"H{i}", f"Dog{i}", i, 0, 30.0 + i) for i in range(7)]
    jump_entries = [_entry(str(100 + i), f"H{i}", f"Dog{i}", i, 0, 20.0 + i) for i in range(7)]
    event = _event(agi_entries, jump_entries)
    with app.test_request_context():
        html = rl._render_bccs_quali_ranking_section(event, _view(laufart="Agility"))
    assert "Quali-Rangliste" in html
    assert "Large" in html and "SM" in html and "Kl.3" in html
    assert "Quote: 2" in html
    assert html.index("Dog0") < html.index("Dog1") < html.index("Dog2")
    # Nur Top 4 angezeigt (Monitor-Platzgrund, wie beim Final)
    assert "Dog4" not in html


def test_quali_ranking_absent_outside_bccs(app):
    event = _event(
        [_entry("100", "Anna", "Fly", 0, 0, 30.0)],
        [_entry("100", "Anna", "Fly", 0, 0, 20.0)],
    )
    event["Veranstaltungsart"] = "Meeting"
    with app.test_request_context():
        assert rl._render_bccs_quali_ranking_section(event, _view()) == ""


def test_quali_ranking_absent_during_final(app):
    event = _event(
        [_entry("100", "Anna", "Fly", 0, 0, 30.0)],
        [_entry("100", "Anna", "Fly", 0, 0, 20.0)],
    )
    with app.test_request_context():
        assert rl._render_bccs_quali_ranking_section(event, _view(is_final=True)) == ""


def test_quali_and_final_sections_mutually_exclusive(app):
    """Während der Quali darf die Final-Kombirangliste nicht erscheinen und
    umgekehrt — beide Karten teilen sich denselben Monitor-Slot."""
    event = _event(
        [_entry("100", "Anna", "Fly", 0, 0, 30.0)],
        [_entry("100", "Anna", "Fly", 0, 0, 20.0)],
    )
    with app.test_request_context():
        quali_html = rl._render_bccs_quali_ranking_section(event, _view(is_final=False))
        final_html = rl._render_bccs_combined_section(event, _view(is_final=False))
    assert quali_html != ""
    assert final_html == ""
