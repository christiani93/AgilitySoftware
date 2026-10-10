import json
import os


def _write_ring_event(event_id="E_LD", ring="Ring 1"):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)
    data_dir = os.path.join(project_root, "data")
    os.makedirs(data_dir, exist_ok=True)

    events_path = os.path.join(data_dir, "events.json")
    event = {
        "id": event_id,
        "name": "Testevent",
        "runs": [
            {"id": "R1", "name": "Agility Large Kl. 3", "klasse": "3", "laufart": "Agility",
             "kategorie": "Large", "assigned_ring": ring, "laufdaten": {}, "entries": []},
            {"id": "R2", "name": "Agility Intermediate Kl. 3", "klasse": "3", "laufart": "Agility",
             "kategorie": "Intermediate", "assigned_ring": ring, "laufdaten": {}, "entries": []},
            {"id": "R3", "name": "Agility Medium Kl. 3", "klasse": "3", "laufart": "Agility",
             "kategorie": "Medium", "assigned_ring": ring, "laufdaten": {}, "entries": []},
            {"id": "R4", "name": "Jumping Large Kl. 1", "klasse": "1", "laufart": "Jumping",
             "kategorie": "Large", "assigned_ring": ring, "laufdaten": {}, "entries": []},
        ]
    }
    with open(events_path, "w", encoding="utf-8") as f:
        json.dump([event], f, indent=2, ensure_ascii=False)
    return event_id


def _runs_by_id(event_id):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)
    events_path = os.path.join(project_root, "data", "events.json")
    with open(events_path, encoding="utf-8") as f:
        events = json.load(f)
    event = next(e for e in events if e["id"] == event_id)
    return {r["id"]: r for r in event["runs"]}


def test_update_laufdaten_single_run_unchanged_behavior(client):
    event_id = _write_ring_event()

    resp = client.post(f"/live/api/update_run_laufdaten/{event_id}/R1", json={
        "parcours_laenge": "180",
        "anzahl_hindernisse": "20",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["applied_to_runs"] == 1

    runs = _runs_by_id(event_id)
    assert runs["R1"]["laufdaten"]["parcours_laenge"] == "180"
    assert runs["R2"]["laufdaten"].get("parcours_laenge") in (None, "")


def test_update_laufdaten_range_applies_to_runs_in_between(client):
    event_id = _write_ring_event()

    resp = client.post(f"/live/api/update_run_laufdaten/{event_id}/R1", json={
        "parcours_laenge": "175",
        "anzahl_hindernisse": "22",
        "until_run_id": "R3",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["applied_to_runs"] == 3

    runs = _runs_by_id(event_id)
    for rid in ("R1", "R2", "R3"):
        assert runs[rid]["laufdaten"]["parcours_laenge"] == "175"
        assert runs[rid]["laufdaten"]["anzahl_hindernisse"] == "22"
    # R4 liegt ausserhalb der Reichweite
    assert runs["R4"]["laufdaten"].get("parcours_laenge") in (None, "")


def test_update_laufdaten_range_different_ring_not_affected(client):
    event_id = _write_ring_event(ring="Ring 1")
    # R4 zusaetzlich auf Ring 2 verschieben, um sicherzustellen, dass ein
    # Range-Versuch ueber Ring-Grenzen hinweg nichts Falsches trifft.
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)
    events_path = os.path.join(project_root, "data", "events.json")
    with open(events_path, encoding="utf-8") as f:
        events = json.load(f)
    event = next(e for e in events if e["id"] == event_id)
    for r in event["runs"]:
        if r["id"] == "R4":
            r["assigned_ring"] = "Ring 2"
    with open(events_path, "w", encoding="utf-8") as f:
        json.dump(events, f)

    resp = client.post(f"/live/api/update_run_laufdaten/{event_id}/R1", json={
        "parcours_laenge": "160",
        "until_run_id": "R4",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    # R4 ist nicht in der Ring-1-Lauf-Liste enthalten -> ValueError -> Fallback auf Einzel-Lauf
    assert data["applied_to_runs"] == 1

    runs = _runs_by_id(event_id)
    assert runs["R1"]["laufdaten"]["parcours_laenge"] == "160"
    assert runs["R4"]["laufdaten"].get("parcours_laenge") in (None, "")
