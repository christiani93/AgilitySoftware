import json
import os


def _write_test_event(event_id="E_PDF", run_id="R_PDF", external_id=None):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)
    data_dir = os.path.join(project_root, "data")
    os.makedirs(data_dir, exist_ok=True)

    events_path = os.path.join(data_dir, "events.json")
    event = {
        "id": event_id,
        "name": "Testevent",
        "external_id": external_id,
        "runs": [{
            "id": run_id,
            "name": "Agility Medium Kl. 2",
            "klasse": "2",
            "laufart": "Agility",
            "kategorie": "Medium",
            "assigned_ring": "Ring 1",
            "laufdaten": {"parcours_laenge": "150"},
            "entries": [
                {"lizenz": "A", "zeit": "34.50", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
                {"lizenz": "B", "zeit": "35.20", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
            ]
        }]
    }
    with open(events_path, "w", encoding="utf-8") as f:
        json.dump([event], f, indent=2, ensure_ascii=False)

    settings_path = os.path.join(data_dir, "settings.json")
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump({
            "portal_url": "https://portal.example.test",
            "portal_results_api_key": "testkey",
            "download_dir": "",
        }, f)

    return event_id, run_id


def test_upload_ranking_pdf_download_only(client, monkeypatch, tmp_path):
    event_id, run_id = _write_test_event(external_id=None)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Downloads").mkdir()

    resp = client.post(f"/live/upload_ranking_pdf/{event_id}/{run_id}", data={
        "is_final": "false",
        "to_portal": "false",
        "to_download": "true",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["download"] == "ok"
    assert os.path.exists(data["download_path"])
    assert str(tmp_path) in data["download_path"]


def test_upload_ranking_pdf_portal_only(client, monkeypatch):
    event_id, run_id = _write_test_event(external_id="EXT123")

    class _FakeResp:
        ok = True
        text = ""

    monkeypatch.setattr("requests.post", lambda *a, **kw: _FakeResp())

    resp = client.post(f"/live/upload_ranking_pdf/{event_id}/{run_id}", data={
        "is_final": "false",
        "to_portal": "true",
        "to_download": "false",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["portal"] == "ok"
    assert "download" not in data


def test_upload_ranking_pdf_both_destinations(client, monkeypatch, tmp_path):
    event_id, run_id = _write_test_event(external_id="EXT123")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Downloads").mkdir()

    class _FakeResp:
        ok = True
        text = ""

    monkeypatch.setattr("requests.post", lambda *a, **kw: _FakeResp())

    resp = client.post(f"/live/upload_ranking_pdf/{event_id}/{run_id}", data={
        "is_final": "true",
        "to_portal": "true",
        "to_download": "true",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["portal"] == "ok"
    assert data["download"] == "ok"


def test_upload_ranking_pdf_neither_destination_selected(client):
    event_id, run_id = _write_test_event(external_id="EXT123")

    resp = client.post(f"/live/upload_ranking_pdf/{event_id}/{run_id}", data={
        "is_final": "false",
        "to_portal": "false",
        "to_download": "false",
    })
    assert resp.status_code == 400


def test_upload_ranking_pdf_portal_without_external_id_errors(client):
    event_id, run_id = _write_test_event(external_id=None)

    resp = client.post(f"/live/upload_ranking_pdf/{event_id}/{run_id}", data={
        "is_final": "false",
        "to_portal": "true",
        "to_download": "false",
    })
    assert resp.status_code == 502
    data = resp.get_json()
    assert "external_id" in data["portal"]
