"""Route-Test für /print/final_startlists/<event_id> (Chris-Wunsch 2026-11-21):
Startlisten der Finalläufe sollen druckbar sein, analog zu
print_final_stewardlists (Ringschreiber) aber als normale Teilnehmer-Startliste.
"""
import json
import os


def _entry(lic, dog, vorname, startnr):
    return {
        "Lizenznummer": lic, "Hundename": dog, "Vorname": vorname, "Nachname": "Muster",
        "Startnummer": startnr,
    }


def _event():
    return {
        "id": "BCCS_FINAL_PRINT_TEST",
        "Bezeichnung": "BCCS-SM Testturnier",
        "runs": [
            {
                "id": "run_agi_kl3", "name": "Agility Kl.3", "kategorie": "Large",
                "klasse": "3", "laufart": "Agility", "is_final": False,
                "laufdaten": {}, "entries": [_entry("L1", "Fly", "Anna", "1")],
            },
            {
                "id": "final_jump_kl3", "name": "Jumping Kl.3 Final", "kategorie": "Large",
                "klasse": "3", "laufart": "Jumping", "is_final": True,
                "laufdaten": {}, "entries": [
                    _entry("L1", "Fly", "Anna", "1"),
                    _entry("L2", "Zoom", "Bea", "2"),
                ],
            },
        ],
    }


def test_print_final_startlists_shows_only_final_runs(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    with open(os.path.join(str(tmp_path), "events.json"), "w", encoding="utf-8") as f:
        json.dump([_event()], f)

    resp = client.get("/print/final_startlists/BCCS_FINAL_PRINT_TEST")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Jumping Kl.3 Final" in html
    assert "Fly" in html and "Zoom" in html
    # Quali-Lauf (nicht final) darf hier nicht auftauchen.
    assert "Agility Kl.3" not in html


def test_print_final_startlists_404_for_unknown_event(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    with open(os.path.join(str(tmp_path), "events.json"), "w", encoding="utf-8") as f:
        json.dump([], f)

    resp = client.get("/print/final_startlists/does-not-exist")
    assert resp.status_code == 404
