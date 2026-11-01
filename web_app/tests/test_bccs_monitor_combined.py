"""
Tests für die BCCS-Zuschauer-/Ring-Monitor-Zusätze (routes_live.py):
  A2  kombinierte Final-Rangliste live (`_render_bccs_combined_table` via
      `_render_bccs_monitor_extras`)
  A3  „Für Platz 1"-Projektion im 2. Finallauf (`_render_bccs_platz1_projection`)

Prüft: Rangfolge in beiden Läufen sauberer Teams, DIS = „nicht klassiert",
Projektion nur im Agility-Final, Fehler-/Zeit-Budget gegen den Kombi-Führenden,
und dass ausserhalb BCCS-SM / bei Nicht-Finalläufen nichts gerendert wird.

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
    }


def _unrun(lic, vorname, dog):
    """Entry eines Hundes, der noch nicht gelaufen ist (keine Rohwerte) → gilt als
    nicht klassiert / „dis" in der Final-Normalisierung."""
    return {"Lizenznummer": lic, "Startnummer": lic, "Vorname": vorname,
            "Nachname": "Test", "Hundename": dog, "disqualifikation": "", "platz": None}


def _event(jump_entries, agi_entries):
    return {
        "Veranstaltungsart": "BCCS-SM",
        "runs": [
            {"kategorie": "Large", "klasse": "3", "laufart": "Jumping",
             "is_final": True, "entries": jump_entries},
            {"kategorie": "Large", "klasse": "3", "laufart": "Agility",
             "is_final": True, "entries": agi_entries},
        ],
    }


def _view(laufart="Agility", starter_lic=None, is_final=True):
    starter = {"Lizenznummer": starter_lic, "Startnummer": starter_lic} if starter_lic else {}
    return {
        "current_run": {"kategorie": "Large", "klasse": "3",
                        "laufart": laufart, "is_final": is_final},
        "current_starter": starter,
    }


# ── A2: kombinierte Rangliste ──────────────────────────────────────────────

def test_combined_table_rendered_and_ordered(app):
    event = _event(
        jump_entries=[
            _entry("100", "Anna", "Fly", 0, 0, 30.00),
            _entry("200", "Bea", "Zoom", 5, 1, 31.00),
            _entry("300", "Cara", "Dash", 999.0, 0, 999.99, dis="DIS"),
        ],
        agi_entries=[
            _entry("100", "Anna", "Fly", 0, 0, 40.00),
            _entry("200", "Bea", "Zoom", 0, 0, 42.00),
            _entry("300", "Cara", "Dash", 0, 0, 45.00),
        ],
    )
    with app.test_request_context():
        html = rl._render_bccs_monitor_extras(event, _view(laufart="Jumping"))
    assert "Kombinierte Rangliste" in html
    assert "Large" in html and "SM" in html
    assert html.index("Fly") < html.index("Zoom")   # Summe 0 vor Summe 5
    assert "Dash" in html and "n. kl." in html        # DIS = nicht klassiert


def test_no_extras_outside_bccs(app):
    event = _event([_entry("100", "Anna", "Fly", 0, 0, 30.0)],
                   [_entry("100", "Anna", "Fly", 0, 0, 40.0)])
    event["Veranstaltungsart"] = "Meeting"
    with app.test_request_context():
        assert rl._render_bccs_monitor_extras(event, _view()) == ""


def test_no_extras_for_non_final(app):
    event = _event([_entry("100", "Anna", "Fly", 0, 0, 30.0)],
                   [_entry("100", "Anna", "Fly", 0, 0, 40.0)])
    with app.test_request_context():
        assert rl._render_bccs_monitor_extras(event, _view(is_final=False)) == ""


# ── A3: Platz-1-Projektion ─────────────────────────────────────────────────

def test_projection_budget_for_current_starter(app):
    # Team 100 bereits fertig (Kombi 0 Fehler / 70 s = Führender).
    # Team 200 (aktueller Starter) hat Jumping (0 Fehler / 31 s), Agility noch offen.
    event = _event(
        jump_entries=[
            _entry("100", "Anna", "Fly", 0, 0, 30.00),
            _entry("200", "Bea", "Zoom", 0, 0, 31.00),
        ],
        agi_entries=[
            _entry("100", "Anna", "Fly", 0, 0, 40.00),
            _unrun("200", "Bea", "Zoom"),
        ],
    )
    with app.test_request_context():
        html = rl._render_bccs_monitor_extras(event, _view(starter_lic="200"))
    assert "Für Platz 1" in html
    assert "Höchstens" in html
    # Fehler-Budget 0, Zeit-Budget 70 - 31 = 39.00 s
    assert "39" in html
    assert "Fly" in html   # Führender genannt


def test_projection_absent_during_jumping(app):
    event = _event(
        jump_entries=[_entry("100", "Anna", "Fly", 0, 0, 30.0),
                      _entry("200", "Bea", "Zoom", 0, 0, 31.0)],
        agi_entries=[_entry("100", "Anna", "Fly", 0, 0, 40.0),
                     _unrun("200", "Bea", "Zoom")],
    )
    with app.test_request_context():
        html = rl._render_bccs_monitor_extras(event, _view(laufart="Jumping", starter_lic="200"))
    assert "Für Platz 1" not in html           # keine Projektion im 1. Finallauf
    assert "Kombinierte Rangliste" in html      # Tabelle trotzdem da


def test_projection_dis_in_jumping(app):
    event = _event(
        jump_entries=[_entry("100", "Anna", "Fly", 0, 0, 30.0),
                      _entry("200", "Bea", "Zoom", 999.0, 0, 999.99, dis="DIS")],
        agi_entries=[_entry("100", "Anna", "Fly", 0, 0, 40.0),
                     _unrun("200", "Bea", "Zoom")],
    )
    with app.test_request_context():
        html = rl._render_bccs_monitor_extras(event, _view(starter_lic="200"))
    assert "Keine Kombination möglich" in html


# ── Division-Auflösung ─────────────────────────────────────────────────────

def test_division_resolved_from_class(app):
    assert rl._bccs_division_for_run({"kategorie": "Intermediate", "klasse": "1"})[1] == "nachwuchs"
    assert rl._bccs_division_for_run({"kategorie": "Intermediate", "klasse": "2"})[1] == "nachwuchs"
    assert rl._bccs_division_for_run({"kategorie": "Large", "klasse": "3"})[1] == "sm"
    assert rl._bccs_division_for_run({"kategorie": "Small", "klasse": "3"}) is None
