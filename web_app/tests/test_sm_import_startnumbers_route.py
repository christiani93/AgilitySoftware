"""Route-Test für die SM-Startnummern-Zuordnung (/sm/import-startnumbers/<event_id>)."""
import io
import json
import os


def _write_event(data_dir, event_id="SM1"):
    event = {
        "id": event_id,
        "Bezeichnung": "SM Test",
        "runs": [
            {"id": "qa", "kategorie": "Large", "laufart": "Agility", "entries": [
                {"Lizenznummer": "111", "Hundename": "Fly", "Startnummer": None},
                {"Lizenznummer": "222", "Hundename": "Zoom", "Startnummer": None},
            ]},
            {"id": "qj", "kategorie": "Large", "laufart": "Jumping", "entries": [
                {"Lizenznummer": "111", "Hundename": "Fly", "Startnummer": None},
                {"Lizenznummer": "222", "Hundename": "Zoom", "Startnummer": None},
            ]},
        ],
    }
    with open(os.path.join(data_dir, "events.json"), "w", encoding="utf-8") as f:
        json.dump([event], f, ensure_ascii=False)


def test_form_renders(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path))
    resp = client.get("/sm/import-startnumbers/SM1")
    assert resp.status_code == 200
    assert "Startnummern".encode("utf-8") in resp.data


def test_404_for_unknown_event(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path))
    resp = client.get("/sm/import-startnumbers/NOPE")
    assert resp.status_code == 404


def test_post_sets_startnumbers_event_wide(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path))
    csv_bytes = b"Lizenznummer;Startnummer\n111;15\n222;16\n"

    resp = client.post(
        "/sm/import-startnumbers/SM1",
        data={"csv": (io.BytesIO(csv_bytes), "start.csv")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/sm/dashboard/SM1" in resp.headers["Location"]

    with open(os.path.join(str(tmp_path), "events.json"), encoding="utf-8") as f:
        events = json.load(f)
    event = events[0]
    for run in event["runs"]:
        nrs = {e["Lizenznummer"]: e["Startnummer"] for e in run["entries"]}
        assert nrs == {"111": "15", "222": "16"}
