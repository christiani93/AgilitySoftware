import json
import os


def _write_event(data_dir, entries):
    """Schreibt ein Testevent mit einem Lauf in ein isoliertes data-Verzeichnis."""
    event = {
        "id": "E1",
        "name": "Scheduling-Test",
        "runs": [{
            "id": "R1",
            "klasse": "2",
            "laufart": "Agility",
            "entries": entries,
        }],
    }
    with open(os.path.join(data_dir, "events.json"), "w", encoding="utf-8") as f:
        json.dump([event], f, indent=2, ensure_ascii=False)


def _load_entry(data_dir, license_nr):
    with open(os.path.join(data_dir, "events.json"), "r", encoding="utf-8") as f:
        run = json.load(f)[0]["runs"][0]
    return next(e for e in run["entries"] if e["Lizenznummer"] == license_nr)


def test_save_result_persists_start_time_tod(client, tmp_path, monkeypatch):
    """Scheduling-Optimierung Schritt 1: die echte TIMY-Startzeit (Tageszeit,
    vom Ring-Server durchgereicht) muss zusammen mit dem Resultat landen,
    statt nur der Speicher-'timestamp' zur Verfügung zu stehen."""
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), [{"Lizenznummer": "L1", "Startnummer": "1"}])

    resp = client.post(
        "/live/save_result/E1/R1",
        json={
            "license_number": "L1",
            "zeit": "34.56",
            "fehler": 0,
            "verweigerungen": 0,
            "disqualifikation": "",
            "start_time_tod": "13:20:16.0431",
        },
    )
    assert resp.status_code == 200
    assert resp.get_json().get("success") is True

    entry = _load_entry(str(tmp_path), "L1")
    assert entry["result"]["start_time_tod"] == "13:20:16.0431"
    assert entry["result"]["zeit"] == "34.56"


def test_save_result_without_start_time_tod_stays_none(client, tmp_path, monkeypatch):
    """Ohne TIMY (manuelle Eingabe) darf das Feld fehlen – kein Pflichtfeld,
    kein Fehler, einfach None statt eines Platzhalterwerts."""
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), [{"Lizenznummer": "L1", "Startnummer": "1"}])

    resp = client.post(
        "/live/save_result/E1/R1",
        json={"license_number": "L1", "zeit": "34.56", "fehler": 0, "verweigerungen": 0},
    )
    assert resp.status_code == 200

    entry = _load_entry(str(tmp_path), "L1")
    assert entry["result"]["start_time_tod"] is None
