"""
Route-/Export-Tests für das SKBS-SM-Blueprint (`routes_skbs_sm.py`).

Ergänzt die reinen Logik-Tests (`tests_pure/test_skbs_sm_qualification.py`) um die
HTTP-Schicht: Dashboard/Final-Liste rendern, CSV-Export-Struktur, Config-POST
(Titelverteidiger setzen/entfernen) und 404 bei unbekanntem Event.

Datenisolation wie die übrigen Route-Tests über `AGILITY_DATA_DIR` → tmp_path,
damit die Suite NIE die echte web_app/data/events.json berührt.
"""
import json
import os


# ── Test-Fixtures (Entries mit result → recalc_and_store rechnet platz) ─────────

def _entry(license_no, zeit, fehler=0, dis=None):
    return {
        "Lizenznummer": license_no,
        "Startnummer":  license_no,           # (Lizenz, Startnr) = recalc-Writeback-Key
        "Hundename":    f"Hund_{license_no}",
        "Vorname":      "Max",
        "Nachname":     f"Muster_{license_no}",
        "result": {
            "zeit":             zeit,
            "fehler":           fehler,
            "verweigerungen":   0,
            "disqualifikation": dis,
        },
    }


def _run(klasse, laufart, entries, is_final=False):
    return {
        "id":        f"R_{klasse}_{laufart}_{'F' if is_final else 'Q'}",
        "kategorie": "Large",
        "klasse":    klasse,
        "laufart":   laufart,
        "is_final":  is_final,
        "laufdaten": {"parcours_laenge": 100},
        "entries":   entries,
    }


def _write_event(data_dir, runs, config=None):
    event = {"id": "E1", "name": "SKBS-SM Testturnier", "runs": runs}
    if config is not None:
        event["skbs_sm_config"] = config
    with open(os.path.join(data_dir, "events.json"), "w", encoding="utf-8") as f:
        json.dump([event], f, indent=2, ensure_ascii=False)


def _load_event(data_dir):
    with open(os.path.join(data_dir, "events.json"), "r", encoding="utf-8") as f:
        return json.load(f)[0]


def _quali_event():
    # Kl.3 Agility + Jumping, je 3 Starter, alle Zeiten < MCT (kein Auto-DIS) →
    # je 3 Finalisten (Quote min 3), 6 eindeutige Lizenzen.
    return [
        _run("3", "Agility", [
            _entry("A", zeit=28), _entry("B", zeit=30), _entry("C", zeit=32),
        ]),
        _run("3", "Jumping", [
            _entry("D", zeit=25), _entry("E", zeit=27), _entry("F", zeit=29),
        ]),
    ]


# ── Dashboard ──────────────────────────────────────────────────────────────────

def test_dashboard_rendert_und_zeigt_finalisten(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), _quali_event())

    resp = client.get("/skbs-sm/dashboard/E1")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Alle 6 direkt Qualifizierten tauchen in der gerenderten Übersicht auf.
    for lic in ("A", "B", "C", "D", "E", "F"):
        assert lic in body


def test_dashboard_unbekanntes_event_404(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), _quali_event())
    assert client.get("/skbs-sm/dashboard/NOPE").status_code == 404


# ── Final-Liste ─────────────────────────────────────────────────────────────────

def test_final_list_rendert(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), _quali_event())
    resp = client.get("/skbs-sm/final-list/E1")
    assert resp.status_code == 200


# ── CSV-Export ──────────────────────────────────────────────────────────────────

def test_export_csv_header_und_finalisten(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), _quali_event())

    resp = client.get("/skbs-sm/export-csv/E1")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "attachment" in resp.headers.get("Content-Disposition", "")

    text = resp.get_data(as_text=True)
    assert "# FINALISTEN" in text
    assert "Lizenznummer" in text
    for lic in ("A", "B", "C", "D", "E", "F"):
        assert lic in text


def test_export_csv_enthaelt_final_rangierung_wenn_final_gelaufen(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    runs = _quali_event()
    # Gemeinsamer Finallauf (is_final) → Final-Rangierungs-Block muss erscheinen.
    runs.append(_run("3", "Agility", [
        _entry("A", zeit=30), _entry("B", zeit=31), _entry("C", zeit=33),
    ], is_final=True))
    _write_event(str(tmp_path), runs)

    text = client.get("/skbs-sm/export-csv/E1").get_data(as_text=True)
    assert "# FINAL-RANGIERUNG" in text
    assert "Final-Rang" in text


def test_export_csv_unbekanntes_event_404(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), _quali_event())
    assert client.get("/skbs-sm/export-csv/NOPE").status_code == 404


# ── Config-POST (Titelverteidiger) ──────────────────────────────────────────────

def test_config_setzt_titelverteidiger(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), _quali_event())

    resp = client.post("/skbs-sm/config/E1", data={
        "defending_license": "CHAMP",
        "defending_dog":     "Vorjahres-Hund",
        "defending_handler": "Vorjahres-HF",
    })
    assert resp.status_code == 302  # redirect aufs Dashboard

    champ = _load_event(str(tmp_path))["skbs_sm_config"]["defending_champion"]
    assert champ["license"] == "CHAMP"
    assert champ["dog_name"] == "Vorjahres-Hund"
    assert champ["handler_name"] == "Vorjahres-HF"


def test_config_leere_lizenz_entfernt_titelverteidiger(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), _quali_event(),
                 config={"defending_champion": {"license": "OLD", "dog_name": "x",
                                                "handler_name": "y"}})

    client.post("/skbs-sm/config/E1", data={"defending_license": ""})

    cfg = _load_event(str(tmp_path))["skbs_sm_config"]
    assert "defending_champion" not in cfg
