"""
Route-/Export-Tests für das FMBB-Quali-Blueprint (`routes_fmbb.py`).

Ergänzt die reinen Logik-Tests (`tests_pure/test_fmbb_quali.py`) um die HTTP-Schicht:
Dashboard rendern, Config-POST (aktivieren/markieren/clear), CSV-Export nur mit
FMBB-markierten Teams und 404 bei unbekanntem Event.

Datenisolation über `AGILITY_DATA_DIR` → tmp_path (NIE die echte events.json).
"""
import json
import os


def _entry(license_no, zeit, is_fmbb=False):
    return {
        "Lizenznummer": license_no,
        "Startnummer":  license_no,
        "Hundename":    f"Hund_{license_no}",
        "Vorname":      "Max",
        "Nachname":     f"Muster_{license_no}",
        "is_fmbb":      is_fmbb,
        "result": {
            "zeit":             zeit,
            "fehler":           0,
            "verweigerungen":   0,
            "disqualifikation": None,
        },
    }


def _run(klasse, laufart, entries):
    return {
        "id":        f"R_{klasse}_{laufart}",
        "kategorie": "Large",
        "klasse":    klasse,
        "laufart":   laufart,
        "laufdaten": {"parcours_laenge": 100},
        "entries":   entries,
    }


def _write_event(data_dir, runs, active=True):
    event = {"id": "E1", "name": "FMBB Testturnier",
             "fmbb_quali_active": active, "runs": runs}
    with open(os.path.join(data_dir, "events.json"), "w", encoding="utf-8") as f:
        json.dump([event], f, indent=2, ensure_ascii=False)


def _load_event(data_dir):
    with open(os.path.join(data_dir, "events.json"), "r", encoding="utf-8") as f:
        return json.load(f)[0]


def _marked_licenses(event):
    out = set()
    for run in event["runs"]:
        for e in run["entries"]:
            if e.get("is_fmbb"):
                out.add(e["Lizenznummer"])
    return out


def _event_two_marked_one_not():
    # Kl.2 Agility: FA/FB als FMBB markiert, NX nicht.
    return [
        _run("2", "Agility", [
            _entry("FA", zeit=28, is_fmbb=True),
            _entry("FB", zeit=30, is_fmbb=True),
            _entry("NX", zeit=26, is_fmbb=False),
        ]),
    ]


# ── Dashboard ──────────────────────────────────────────────────────────────────

def test_dashboard_rendert(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), _event_two_marked_one_not())
    resp = client.get("/fmbb/dashboard/E1")
    assert resp.status_code == 200


def test_dashboard_unbekanntes_event_404(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), _event_two_marked_one_not())
    assert client.get("/fmbb/dashboard/NOPE").status_code == 404


# ── CSV-Export (nur markierte Teams) ────────────────────────────────────────────

def test_export_csv_nur_markierte_teams(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), _event_two_marked_one_not())

    resp = client.get("/fmbb/export-csv/E1")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "attachment" in resp.headers.get("Content-Disposition", "")

    text = resp.get_data(as_text=True)
    assert "Lizenznummer" in text
    assert "FA" in text and "FB" in text
    # Nicht markiertes Team darf NICHT im FMBB-Export erscheinen.
    assert "NX" not in text


def test_export_csv_unbekanntes_event_404(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), _event_two_marked_one_not())
    assert client.get("/fmbb/export-csv/NOPE").status_code == 404


# ── Config-POST: aktivieren / deaktivieren ──────────────────────────────────────

def test_config_activate_deactivate(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), _event_two_marked_one_not(), active=False)

    client.post("/fmbb/config/E1", data={"action": "activate"})
    assert _load_event(str(tmp_path))["fmbb_quali_active"] is True

    client.post("/fmbb/config/E1", data={"action": "deactivate"})
    assert _load_event(str(tmp_path))["fmbb_quali_active"] is False


# ── Config-POST: Bulk-Marker via Lizenzliste ────────────────────────────────────

def test_config_mark_licenses_setzt_flags(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    # Start: keiner markiert.
    runs = [
        _run("2", "Agility", [
            _entry("L1", zeit=28), _entry("L2", zeit=30), _entry("L3", zeit=26),
        ]),
    ]
    _write_event(str(tmp_path), runs)

    resp = client.post("/fmbb/config/E1", data={
        "action":   "mark_licenses",
        "licenses": "L1, L3\nUNBEKANNT",   # gemischte Trennzeichen + 1 unbekannte
        "reset":    "1",
    })
    assert resp.status_code == 302

    marked = _marked_licenses(_load_event(str(tmp_path)))
    assert marked == {"L1", "L3"}          # L2 nicht, UNBEKANNT ignoriert


def test_config_clear_marks_setzt_zurueck(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), _event_two_marked_one_not())
    # Vorbedingung: FA/FB markiert.
    assert _marked_licenses(_load_event(str(tmp_path))) == {"FA", "FB"}

    client.post("/fmbb/config/E1", data={"action": "clear_marks"})
    assert _marked_licenses(_load_event(str(tmp_path))) == set()
