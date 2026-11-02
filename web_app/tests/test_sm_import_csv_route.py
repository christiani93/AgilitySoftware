"""Route-Test für den SM-Resultat-Import (/sm/import-csv).

Deckt ab: GET zeigt das Formular, POST baut ein eigenständiges Event aus
Quali-(+Final-)CSV, gleiche Event-ID überschreibt, fehlende Quali-Datei →
Redirect mit Flash statt Crash.
"""
import io
import json
import os


def _row(lic, dog, hf, kat, kl, rang, zeit, fehler, verw, dis, lauf,
         parcours="200", geraete="20"):
    return ";".join(str(x) for x in [
        "9999", lic, dog, hf, "0", kat, kl, rang, zeit, "5.0", fehler, verw,
        "0.00", "0.00", dis, lauf, "22115", parcours, geraete, "48.00", "84.0",
        "14.09.2024", "", "", "",
    ])


_HEADER = "Lizenznummer;Hundename;Hundefuehrer;Club;Kategorie;Klasse;Rang"


def _csv_bytes(*rows):
    return ("\n".join([_HEADER, *rows])).encode("utf-8")


def test_import_csv_form_renders(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    resp = client.get("/sm/import-csv")
    assert resp.status_code == 200
    assert b"Resultat-Import" in resp.data


def test_import_csv_builds_event_from_quali_and_final(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    quali = _csv_bytes(
        _row("111", "Fly", "Anna Meier", "Large", "3", "1", "35.00", "0", "0", "", "Agility"),
        _row("111", "Fly", "Anna Meier", "Large", "3", "1", "33.00", "0", "0", "", "Jumping"),
    )
    final = _csv_bytes(
        _row("111", "Fly", "Anna Meier", "Large", "3", "1", "36.00", "0", "0", "", "Agility"),
        _row("111", "Fly", "Anna Meier", "Large", "3", "1", "34.00", "0", "0", "", "Jumping"),
    )
    resp = client.post(
        "/sm/import-csv",
        data={
            "quali_csv": (io.BytesIO(quali), "quali.csv"),
            "final_csv": (io.BytesIO(final), "final.csv"),
            "event_id": "SM_TEST",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/sm/dashboard/SM_TEST" in resp.headers["Location"]

    with open(os.path.join(str(tmp_path), "events.json"), encoding="utf-8") as f:
        events = json.load(f)
    event = next(e for e in events if e["id"] == "SM_TEST")
    types = {r["sm_run_type"] for r in event["runs"]}
    assert types == {"qual_agility", "qual_jumping", "final_agility", "final_jumping"}


def test_import_csv_same_id_overwrites(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    quali_v1 = _csv_bytes(_row("111", "Fly", "A B", "Large", "3", "1", "35.0", "0", "0", "", "Agility"))
    quali_v2 = _csv_bytes(_row("222", "Zoom", "C D", "Small", "3", "1", "30.0", "0", "0", "", "Agility"))

    for payload in (quali_v1, quali_v2):
        client.post(
            "/sm/import-csv",
            data={"quali_csv": (io.BytesIO(payload), "quali.csv"), "event_id": "SM_TEST2"},
            content_type="multipart/form-data",
        )

    with open(os.path.join(str(tmp_path), "events.json"), encoding="utf-8") as f:
        events = json.load(f)
    matching = [e for e in events if e["id"] == "SM_TEST2"]
    assert len(matching) == 1  # nicht dupliziert
    lics = {e["Lizenznummer"] for r in matching[0]["runs"] for e in r["entries"]}
    assert lics == {"222"}  # v2 hat v1 ersetzt, nicht ergaenzt


def test_import_csv_missing_quali_file_redirects_with_flash(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    resp = client.post("/sm/import-csv", data={"event_id": "SM_TEST3"},
                        content_type="multipart/form-data", follow_redirects=True)
    assert resp.status_code == 200
    assert "Keine Quali-Datei".encode("utf-8") in resp.data
