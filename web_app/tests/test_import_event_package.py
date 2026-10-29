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
    assert events[0]["Bezeichnung"] == "Testevent"
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


def _build_eventexport_zip_with_final_block() -> bytes:
    """Portal-Export eines Finalblocks (American/KO) auf Ring 3, Portal-Pendant
    routes.py:2426 (block_type='final', final_participants=Gesamtzahl, kein
    discipline/category_code)."""
    manifest = {"schema": "agility.exchange.eventexport.v1"}
    event = {"event": {"Bezeichnung": "HCS Final-Import-Test", "Datum": "2026-10-31"}}
    entities = {"persons": [], "dogs": []}
    registrations = {"registrations": []}
    schedule = {
        "ring_start_times": {"3": "08:00"},
        "blocks": [
            {"ring": 3, "sort_index": 0, "block_type": "final",
             "title": "Finale", "final_participants": 32,
             "duration_minutes": 128, "notes": ""},
        ],
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("event.json", json.dumps(event))
        zf.writestr("entities.json", json.dumps(entities))
        zf.writestr("registrations.json", json.dumps(registrations))
        zf.writestr("start_numbers.json", json.dumps([]))
        zf.writestr("schedule.json", json.dumps(schedule))
    return buf.getvalue()


def test_import_final_block_becomes_final_not_run(client, tmp_path, monkeypatch):
    """Regression: ein exportierter Finalblock (block_type='final') darf beim
    Import NICHT als normaler 'run'-Block mit leerer Disziplin/Kategorie
    landen (das rechnete 0 Teilnehmer / falsche Dauer), sondern muss als
    type='final' mit participant_count_override aus final_participants
    ankommen (Portal-Parity-Port 2026-10-29)."""
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    zip_bytes = _build_eventexport_zip_with_final_block()

    resp = client.post(
        "/events/import_package",
        data={"package_file": (io.BytesIO(zip_bytes), "event_export.zip")},
        content_type="multipart/form-data",
    )
    assert resp.status_code in (302, 200)

    events = json.loads((tmp_path / "events.json").read_text(encoding="utf-8"))
    assert len(events) == 1
    blocks = events[0]["schedule"]["rings"]["3"]["blocks"]
    assert len(blocks) == 1
    final_block = blocks[0]
    assert final_block["type"] == "final"
    assert final_block["title"] == "Finale"
    assert final_block["participant_count_override"] == 32
    assert "discipline" not in final_block and "size_category" not in final_block
