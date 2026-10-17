"""
Smoke-/Regressionstest fuer die Portal-Parity-Umstellung des Zeitplan-Moduls:
Ein Event mit einem NICHT-atomaren Zeitplan-Block (eine Disziplin, alle
Kategorien, eine Klasse) muss beim Laden automatisch auf atomare Bloecke
migriert werden, und alle zeitplan-/druckbasierten View-Routen muessen ohne
Crash rendern. Deckt den Bruchpunkt ab, dass die alte Timeline-Engine atomare
Bloecke falsch gruppiert haette.
"""
import json
import os

import pytest

from app import app as flask_app
import utils
import planner.schedule_planner as sp


def _data_dir():
    base = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base)      # web_app/
    d = os.path.join(project_root, "data")
    os.makedirs(d, exist_ok=True)
    return d


def _seed_event():
    ev = {
        "id": "SMOKE",
        "name": "Smoke Zeitplan",
        "Datum": "2026-10-30",
        "num_rings": 1,
        "start_times_by_ring": {"ring_1": "08:00"},
        "runs": [],
        "run_order": [],
        "schedule": {
            "schedule_version": 1,
            "event_id": "SMOKE",
            "meta": {},
            "rings": {
                "1": {
                    "start_time": "08:00",
                    "blocks": [
                        # NICHT-atomar: Agility, alle Kategorien, Klasse 1
                        {
                            "id": "blk_multi",
                            "type": "run",
                            "title": "",
                            "run_format": "normal",
                            "timing_run_type": "agility",
                            "size_category": "all",
                            "size_categories": [],
                            "classes": ["1"],
                            "judge_id": "",
                            "sort": {
                                "primary": {"field": "category", "direction": "asc"},
                                "secondary": {"field": "class", "direction": "asc"},
                            },
                            "estimated": {},
                            "notes": "",
                        },
                    ],
                }
            },
        },
    }
    # je Kategorie ein Lauf mit ein paar Startern
    for cat in ("Large", "Intermediate", "Medium", "Small"):
        ev["runs"].append({
            "id": f"R_{cat}",
            "laufart": "Agility",
            "kategorie": cat,
            "klasse": "1",
            "laufdaten": {"parcours_laenge": "150"},
            "entries": [
                {"Lizenznummer": f"{cat[:1]}{i}", "Startnummer": str(100 + i),
                 "Hundename": f"Dog{i}", "Hundefuehrer": f"HF{i}",
                 "zeit": "", "fehler": "", "verweigerungen": "", "dis_abr": ""}
                for i in range(3)
            ],
        })
    with open(os.path.join(_data_dir(), "events.json"), "w", encoding="utf-8") as f:
        json.dump([ev], f, ensure_ascii=False, indent=2)
    return ev


@pytest.fixture
def client():
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


def test_nonatomic_block_migrates_and_groups_as_one():
    ev = _seed_event()
    # ensure_schedule_root migriert idempotent beim Normalisieren
    schedule = sp.ensure_schedule_root("SMOKE", 1, {"ring_1": "08:00"}, ev["schedule"])
    blocks = schedule["rings"]["1"]["blocks"]
    assert len(blocks) == 4                       # 4 Kategorien x Kl.1 -> atomar
    assert all(sp._is_atomic_run_block(b) for b in blocks)

    # Parity-Timeline: gleiche Disziplin+Klasse -> EINE Gruppe (ein Umbau/Briefing)
    ev["schedule"] = schedule
    tl = utils._calculate_timelines(ev)
    segs = tl.get("1", [])
    changeovers = [s for s in segs if s.get("segment_type") == "changeover"]
    briefings = [s for s in segs if s.get("segment_type") == "briefing"]
    runs = [s for s in segs if s.get("segment_type") == "run"]
    assert len(changeovers) == 1                  # NICHT 4 (wie alte Engine)
    assert len(briefings) == 1
    assert len(runs) == 4                          # ein Lauf-Segment pro Kategorie
    # Kompat-Aliasse vorhanden
    assert all("num_starters" in s and "duration" in s for s in segs)


@pytest.mark.parametrize("url", [
    "/events/plan_schedule/SMOKE",
    "/print/schedule/SMOKE",
    "/print/briefing_groups/SMOKE",
    "/print/all/SMOKE",
    "/print/startlists_by_schedule/SMOKE",
])
def test_schedule_and_print_routes_render(client, url):
    _seed_event()
    resp = client.get(url)
    assert resp.status_code == 200, f"{url} -> {resp.status_code}"
