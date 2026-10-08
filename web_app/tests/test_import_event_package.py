import io
import json
import zipfile


def _build_eventexport_zip(with_logo: bool = True) -> bytes:
    manifest = {"schema": "agility.exchange.eventexport.v1"}
    event = {"event": {"Bezeichnung": "Testevent", "Datum": "2026-10-11"}}
    entities = {"persons": [], "dogs": []}
    registrations = {"registrations": []}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("event.json", json.dumps(event))
        zf.writestr("entities.json", json.dumps(entities))
        zf.writestr("registrations.json", json.dumps(registrations))
        zf.writestr("start_numbers.json", json.dumps([]))
        zf.writestr("schedule.json", json.dumps([]))
        if with_logo:
            zf.writestr("logos/event_logo.png", b"fake-png-bytes")
    return buf.getvalue()


def test_import_zip_with_logo_does_not_crash(client, tmp_path, monkeypatch):
    """Regression: Logo-Extraktion griff nach Schliessen des with-Blocks auf
    zip_file zu ('Attempt to use ZIP archive that was already closed'),
    sobald das ZIP einen logos/-Eintrag enthielt."""
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    zip_bytes = _build_eventexport_zip(with_logo=True)

    resp = client.post(
        "/events/import_package",
        data={"package_file": (io.BytesIO(zip_bytes), "event_export.zip")},
        content_type="multipart/form-data",
    )

    assert resp.status_code in (302, 200)
    assert b"already closed" not in resp.data

    events = json.loads((tmp_path / "events.json").read_text(encoding="utf-8"))
    assert len(events) == 1
    assert events[0]["Bezeichnung"] == "Testevent (Importiert)"
    assert events[0].get("event_logo_filename") == "event_logo.png"


def test_import_zip_without_logo_still_works(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    zip_bytes = _build_eventexport_zip(with_logo=False)

    resp = client.post(
        "/events/import_package",
        data={"package_file": (io.BytesIO(zip_bytes), "event_export.zip")},
        content_type="multipart/form-data",
    )

    assert resp.status_code in (302, 200)
    events = json.loads((tmp_path / "events.json").read_text(encoding="utf-8"))
    assert len(events) == 1
