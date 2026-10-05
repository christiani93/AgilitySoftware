import json
import os


def _write_event(data_dir, entries, current_license):
    """Schreibt ein Testevent mit einem Lauf in ein isoliertes data-Verzeichnis."""
    event = {
        "id": "E1",
        "name": "Statustest",
        "runs": [{
            "id": "R1",
            "klasse": "2",
            "laufart": "Agility",
            "entries": entries,
            "current_starter": next(
                (e for e in entries if e["Lizenznummer"] == current_license), {}
            ),
        }],
    }
    with open(os.path.join(data_dir, "events.json"), "w", encoding="utf-8") as f:
        json.dump([event], f, indent=2, ensure_ascii=False)


def _load_run(data_dir):
    with open(os.path.join(data_dir, "events.json"), "r", encoding="utf-8") as f:
        return json.load(f)[0]["runs"][0]


def test_dns_advances_current_starter(client, tmp_path, monkeypatch):
    """DNS beendet den Eintrag und muss – wie DIS – current/next_starter
    weiterrücken, damit der aktive Läufer nicht auf dem gesetzten Teilnehmer
    stehen bleibt (Regression: DNS-Zweig hatte keine Fortschalt-Logik)."""
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    entries = [
        {"Lizenznummer": "L1", "Startnummer": "1"},
        {"Lizenznummer": "L2", "Startnummer": "2"},
        {"Lizenznummer": "L3", "Startnummer": "3"},
    ]
    _write_event(str(tmp_path), entries, current_license="L1")

    resp = client.post(
        "/live/api/set_participant_status/E1/R1",
        json={"license_number": "L1", "status": "DNS"},
    )
    assert resp.status_code == 200
    assert resp.get_json().get("success") is True

    run = _load_run(str(tmp_path))
    assert run["entries"][0]["result"]["disqualifikation"] == "DNS"
    # Aktiver Läufer ist jetzt L2, bereit steht L3
    assert run["current_starter"].get("Lizenznummer") == "L2"
    assert run["next_starter"].get("Lizenznummer") == "L3"


def test_dns_on_later_participant_keeps_current(client, tmp_path, monkeypatch):
    """DNS für einen späteren (nicht aktiven) Teilnehmer darf den aktuellen
    Starter nicht verändern – nur der DNS-Eintrag fällt aus der Startreihenfolge."""
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    entries = [
        {"Lizenznummer": "L1", "Startnummer": "1"},
        {"Lizenznummer": "L2", "Startnummer": "2"},
        {"Lizenznummer": "L3", "Startnummer": "3"},
    ]
    _write_event(str(tmp_path), entries, current_license="L1")

    resp = client.post(
        "/live/api/set_participant_status/E1/R1",
        json={"license_number": "L3", "status": "DNS"},
    )
    assert resp.status_code == 200

    run = _load_run(str(tmp_path))
    # Aktiver Läufer bleibt L1, bereit ist L2 (L3 ist raus)
    assert run["current_starter"].get("Lizenznummer") == "L1"
    assert run["next_starter"].get("Lizenznummer") == "L2"
