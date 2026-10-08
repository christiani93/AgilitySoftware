import json
import os


def _write_event(data_dir, license_nr):
    """Schreibt ein Testevent mit zwei Läufen (Agility + Jumping), in denen
    dieselbe Hündin startet – so prüfen wir, dass der Toggle auf ALLE Läufe
    wirkt."""
    event = {
        "id": "E1",
        "name": "Läufig-Test",
        "runs": [
            {
                "id": "R1",
                "klasse": "2",
                "laufart": "Agility",
                "kategorie": "Small",
                "entries": [
                    {"Lizenznummer": license_nr, "Startnummer": "5"},
                    {"Lizenznummer": "L999", "Startnummer": "6"},
                ],
            },
            {
                "id": "R2",
                "klasse": "2",
                "laufart": "Jumping",
                "kategorie": "Small",
                "entries": [
                    {"Lizenznummer": license_nr, "Startnummer": "5"},
                ],
            },
        ],
    }
    with open(os.path.join(data_dir, "events.json"), "w", encoding="utf-8") as f:
        json.dump([event], f, indent=2, ensure_ascii=False)


def _load_runs(data_dir):
    with open(os.path.join(data_dir, "events.json"), "r", encoding="utf-8") as f:
        return json.load(f)[0]["runs"]


def _season_flags(runs, license_nr):
    return [
        bool(p.get("is_in_season"))
        for r in runs
        for p in r["entries"]
        if p["Lizenznummer"] == license_nr
    ]


def test_toggle_in_season_sets_all_runs(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), "L1")

    resp = client.post("/events/api/toggle_in_season/E1/L1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["is_in_season"] is True

    runs = _load_runs(str(tmp_path))
    # Beide Läufe der Hündin sind jetzt läufig, der andere Hund bleibt unberührt.
    assert _season_flags(runs, "L1") == [True, True]
    assert _season_flags(runs, "L999") == [False]


def test_toggle_in_season_is_reversible(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), "L1")

    client.post("/events/api/toggle_in_season/E1/L1")
    resp = client.post("/events/api/toggle_in_season/E1/L1")
    assert resp.get_json()["is_in_season"] is False

    runs = _load_runs(str(tmp_path))
    assert _season_flags(runs, "L1") == [False, False]


def test_toggle_in_season_unknown_license_404(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AGILITY_DATA_DIR", str(tmp_path))
    _write_event(str(tmp_path), "L1")

    resp = client.post("/events/api/toggle_in_season/E1/NOPE")
    assert resp.status_code == 404
    assert resp.get_json()["success"] is False
