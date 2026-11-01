"""
Globaler Einweiser-Anzeigemodus (HCS-Wunsch 31.10.): KO↔Normal-Umschalter.

Kernlogik `_effective_ko_mode` (pur) + Guard der Umschalt-Route
`POST /einweiser/api/set_mode`. Der Erfolgspfad der Route wird hier NICHT
getestet, weil er `events.json` mutiert (würde Dev-Daten verändern) — nur der
Validierungs-Guard (ungültiger Modus → 400, vor jedem Load/Save).
"""
import blueprints.routes_einweiser as ew


def test_effective_ko_mode_auto_with_finals():
    assert ew._effective_ko_mode({'ko_cup': {'finals': [{'x': 1}]}}) is True


def test_effective_ko_mode_auto_without_finals():
    assert ew._effective_ko_mode({}) is False
    assert ew._effective_ko_mode({'ko_cup': {'finals': []}}) is False


def test_effective_ko_mode_force_ko_without_finals():
    # Override 'ko' erzwingt KO-Anzeige auch ohne konfigurierte Finals.
    assert ew._effective_ko_mode({'einweiser_mode': 'ko'}) is True


def test_effective_ko_mode_force_normal_with_finals():
    # Override 'normal' erzwingt Normal-Läufe trotz konfigurierter Finals (der Kern
    # des HCS-Wunsches: während des KO einen normalen Ring am Einweiser vorbereiten).
    ev = {'einweiser_mode': 'normal', 'ko_cup': {'finals': [{'x': 1}]}}
    assert ew._effective_ko_mode(ev) is False


def test_set_mode_rejects_invalid_mode(client):
    r = client.post('/einweiser/api/set_mode', json={'mode': 'bogus'})
    assert r.status_code == 400
    assert r.get_json()['success'] is False
