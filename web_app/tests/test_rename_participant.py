import json
import os


def _write_event(data_dir):
    """Testevent mit zwei Läufen (Agility + Jumping), in denen dieselbe
    Lizenznummer startet – so prüfen wir, dass Rename event-weit wirkt."""
    event = {
        "id": "E1",
        "name": "Rename-Test",
        "runs": [
            {
                "id": "R1",
                "klasse": "2",
                "laufart": "Agility",
                "kategorie": "Small",
                "entries": [
                    {"Lizenznummer": "L1", "Startnummer": "5",
                     "Hundefuehrer": "Alt Name", "Hundename": "Alt Hund"},
                    {"Lizenznummer": "L999", "Startnummer": "6",
                     "Hundefuehrer": "Andere Person", "Hundename": "Anderer Hund"},
                ],
            },
            {
                "id": "R2",
                "klasse": "2",
                "laufart": "Jumping",
                "kategorie": "Small",
                "entries": [
                    {"Lizenznummer": "L1", "Startnummer": "5",
                     "Hundefuehrer": "Alt Name", "Hundename": "Alt Hund"},
                ],
            },
        ],
    }
    with open(os.path.join(data_dir, "events.json"), "w", encoding="utf-8") as f:
        json.dump([event], f, indent=2, ensure_ascii=False)


def _entries(data_dir, license_nr):
    with open(os.path.join(data_dir, "events.json"), "r", encoding="utf-8") as f:
        runs = json.load(f)[0]["runs"]
    return [p for r in runs for p in r["entries"] if p["Lizenznummer"] == license_nr]


def test_rename_updates_all_runs(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path))

    resp = client.post("/events/api/rename_participant/E1/L1",
                       json={"Hundefuehrer": "Neu Name", "Hundename": "Neu Hund"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["changed"] == 2

    for p in _entries(str(tmp_path), "L1"):
        assert p["Hundefuehrer"] == "Neu Name"
        assert p["Hundename"] == "Neu Hund"
        assert p["Startnummer"] == "5"  # Startnummer bleibt
    # andere Starter unberührt
    other = _entries(str(tmp_path), "L999")[0]
    assert other["Hundefuehrer"] == "Andere Person"


def test_rename_only_handler(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path))

    resp = client.post("/events/api/rename_participant/E1/L1",
                       json={"Hundefuehrer": "Nur HF"})
    assert resp.status_code == 200
    for p in _entries(str(tmp_path), "L1"):
        assert p["Hundefuehrer"] == "Nur HF"
        assert p["Hundename"] == "Alt Hund"  # unverändert


def test_rename_empty_payload_400(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path))

    resp = client.post("/events/api/rename_participant/E1/L1",
                       json={"Hundefuehrer": "  ", "Hundename": ""})
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_rename_unknown_license_404(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path))

    resp = client.post("/events/api/rename_participant/E1/NOPE",
                       json={"Hundefuehrer": "X"})
    assert resp.status_code == 404
    assert resp.get_json()["success"] is False
