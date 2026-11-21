import io
import json
import zipfile


def test_merge_eventexport_dogs_propagates_extra_fields():
    """Portal-Event-Paket liefert Zusatzfelder (SHSB/Leistungsbuch/FAPAC/Sexe/
    Chip) in entities.dogs[] — der Import muss sie auf die Software-Keys mappen."""
    from web_app.blueprints.routes_events import _merge_eventexport_dogs

    dogs = []
    entities = {
        "dogs": [
            {
                "external_id": "dog_ext1",
                "license_no": "12345",
                "name": "Rex",
                "breed": "Border Collie",
                "sexe": "M",
                "shsb": "SHSB-99887",
                "chip": "756098100000001",
            },
            {
                "external_id": "dog_ext2",
                "license_no": "DEU-77",
                "name": "Bello",
                "sexe": "F",
                "leistungsbuch": "K-33333",
            },
        ]
    }
    _merge_eventexport_dogs(dogs, entities, handler_external_map={})

    by_lic = {d["Lizenznummer"]: d for d in dogs}
    assert by_lic["12345"]["SHSB"] == "SHSB-99887"
    assert by_lic["12345"]["Sexe"] == "M"
    assert by_lic["12345"]["Chip"] == "756098100000001"
    assert by_lic["DEU-77"]["Leistungsbuch"] == "K-33333"
    assert by_lic["DEU-77"]["Sexe"] == "F"


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


def test_import_zip_with_title_defenders_fills_bccs_sm_config(client, tmp_path, monkeypatch):
    """Portal-Export liefert title_defenders.json (EventFinalist source=
    'title_defender') → muss in event['bccs_sm_config']['defending_champions']
    landen (von bccs_sm_qualification.py._find_defender gelesen)."""
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    manifest = {"schema": "agility.exchange.eventexport.v1"}
    event = {"event": {"Bezeichnung": "BCCS-TV-Import-Test", "Datum": "2026-11-22"}}
    entities = {"persons": [], "dogs": []}
    registrations = {"registrations": []}
    title_defenders = {"title_defenders": [
        {"license": "16790", "dog_name": "Win", "handler_name": "Jeannine Gloor",
         "category": "Large", "division": "nachwuchs"},
        {"license": "16480", "dog_name": "Beany", "handler_name": "Anita Leonardi",
         "category": "Intermediate", "division": "nachwuchs"},
    ]}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("event.json", json.dumps(event))
        zf.writestr("entities.json", json.dumps(entities))
        zf.writestr("registrations.json", json.dumps(registrations))
        zf.writestr("start_numbers.json", json.dumps([]))
        zf.writestr("schedule.json", json.dumps([]))
        zf.writestr("title_defenders.json", json.dumps(title_defenders))
    zip_bytes = buf.getvalue()

    resp = client.post(
        "/events/import_package",
        data={"package_file": (io.BytesIO(zip_bytes), "event_export.zip")},
        content_type="multipart/form-data",
    )
    assert resp.status_code in (302, 200)

    events = json.loads((tmp_path / "events.json").read_text(encoding="utf-8"))
    assert len(events) == 1
    defenders = events[0]["bccs_sm_config"]["defending_champions"]
    assert {d["license"] for d in defenders} == {"16790", "16480"}
    win = next(d for d in defenders if d["license"] == "16790")
    assert win["dog_name"] == "Win"
    assert win["division"] == "nachwuchs"


def test_import_zip_without_title_defenders_leaves_config_empty(client, tmp_path, monkeypatch):
    """Kein title_defenders.json im ZIP (ältere Exporte/andere Veranstaltungsart)
    darf den Import nicht brechen und darf keine leere Config erzwingen."""
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    zip_bytes = _build_eventexport_zip(with_logo=False)

    resp = client.post(
        "/events/import_package",
        data={"package_file": (io.BytesIO(zip_bytes), "event_export.zip")},
        content_type="multipart/form-data",
    )
    assert resp.status_code in (302, 200)
    events = json.loads((tmp_path / "events.json").read_text(encoding="utf-8"))
    assert "bccs_sm_config" not in events[0] or not events[0]["bccs_sm_config"].get("defending_champions")


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
        "grossring_rings": ["3"],
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
    assert events[0]["grossring_rings"] == ["3"]
