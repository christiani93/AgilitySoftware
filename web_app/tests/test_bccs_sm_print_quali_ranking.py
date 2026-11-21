"""Route-Test für die BCCS-SM Quali-Ranglisten-Druckseite
(/print/bccs_sm_quali_ranking/<event_id>/<run_id>).

Deckt den Chris-Wunsch ab: Quali-Ranglisten der BCCS-SM-Läufe sollen druck-/
PDF-exportierbar sein (Browser-Druck wie die übrigen print_bp-Ranglisten).
"""
import json
import os


def _entry(lic, dog, hf, fehler_total, zeit_total, startnr):
    return {
        "Lizenznummer": lic, "Hundename": dog, "Vorname": hf, "Nachname": "Muster",
        "Startnummer": startnr, "fehler_total": fehler_total, "fehler_parcours": 0,
        "zeit_total": zeit_total, "disqualifikation": "", "platz": None,
        "bccs_sm": True,
    }


def _event():
    return {
        "id": "BCCS_PRINT_TEST",
        "Bezeichnung": "BCCS-SM Testturnier",
        "runs": [
            {
                "id": "run_agi_kl3", "name": "Agility Kl.3", "kategorie": "Large",
                "klasse": "3", "laufart": "Agility", "is_final": False,
                "laufdaten": {}, "entries": [
                    _entry("L1", "Fly", "Anna", 0, 30.0, "1"),
                    _entry("L2", "Zoom", "Bea", 5, 31.0, "2"),
                ],
            },
            {
                "id": "run_jump_kl3", "name": "Jumping Kl.3", "kategorie": "Large",
                "klasse": "3", "laufart": "Jumping", "is_final": False,
                "laufdaten": {}, "entries": [
                    _entry("L1", "Fly", "Anna", 0, 20.0, "1"),
                    _entry("L2", "Zoom", "Bea", 0, 19.0, "2"),
                ],
            },
        ],
    }


def test_print_bccs_sm_quali_ranking_renders_full_list(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    with open(os.path.join(str(tmp_path), "events.json"), "w", encoding="utf-8") as f:
        json.dump([_event()], f)

    resp = client.get("/print/bccs_sm_quali_ranking/BCCS_PRINT_TEST/run_agi_kl3")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    # Beide Starter der Quali (nicht nur Finalisten) sind auf der Liste.
    assert "Fly" in html
    assert "Zoom" in html
    assert "Anna" in html and "Bea" in html


def test_print_bccs_sm_quali_ranking_404_for_final_run(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    event = _event()
    event["runs"][0]["is_final"] = True
    with open(os.path.join(str(tmp_path), "events.json"), "w", encoding="utf-8") as f:
        json.dump([event], f)

    resp = client.get("/print/bccs_sm_quali_ranking/BCCS_PRINT_TEST/run_agi_kl3")
    assert resp.status_code == 404
