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


def _seed_atomic_two_blocks():
    ev = {
        "id": "EDIT",
        "name": "Editor Test",
        "Datum": "2026-10-30",
        "num_rings": 1,
        "start_times_by_ring": {"ring_1": "08:00"},
        "runs": [
            {"id": "RL", "laufart": "Agility", "kategorie": "Large", "klasse": "1",
             "laufdaten": {"parcours_laenge": "150"}, "entries": []},
            {"id": "RM", "laufart": "Agility", "kategorie": "Medium", "klasse": "1",
             "laufdaten": {"parcours_laenge": "150"}, "entries": []},
        ],
        "run_order": [],
        "schedule": {"schedule_version": 2, "event_id": "EDIT", "meta": {}, "rings": {"1": {
            "start_time": "08:00", "blocks": [
                {"id": "A", "type": "run", "timing_run_type": "agility", "size_category": "large",
                 "size_categories": [], "classes": ["1"], "judge_id": "", "title": "",
                 "sort_index": 0, "skip_changeover": False, "skip_briefing": False,
                 "force_new_group": False, "participant_count_override": None, "run_id": None},
                {"id": "B", "type": "run", "timing_run_type": "agility", "size_category": "medium",
                 "size_categories": [], "classes": ["1"], "judge_id": "", "title": "",
                 "sort_index": 10, "skip_changeover": False, "skip_briefing": False,
                 "force_new_group": False, "participant_count_override": None, "run_id": None},
            ]}}},
    }
    with open(os.path.join(_data_dir(), "events.json"), "w", encoding="utf-8") as f:
        json.dump([ev], f, ensure_ascii=False, indent=2)


def _load_block(block_id):
    with open(os.path.join(_data_dir(), "events.json"), encoding="utf-8") as f:
        ev = json.load(f)[0]
    for b in ev["schedule"]["rings"]["1"]["blocks"]:
        if b["id"] == block_id:
            return b
    return None


def test_toggle_route_sets_force_new_group(client):
    _seed_atomic_two_blocks()
    resp = client.post("/events/plan_schedule/EDIT/toggle_block",
                       data={"block_id": "B", "field": "new_group"})
    assert resp.status_code == 302
    assert _load_block("B")["force_new_group"] is True
    # erneutes Togglen hebt wieder auf
    client.post("/events/plan_schedule/EDIT/toggle_block",
                data={"block_id": "B", "field": "new_group"})
    assert _load_block("B")["force_new_group"] is False


def test_toggle_route_skip_changeover_and_briefing(client):
    _seed_atomic_two_blocks()
    client.post("/events/plan_schedule/EDIT/toggle_block",
                data={"block_id": "A", "field": "changeover"})
    client.post("/events/plan_schedule/EDIT/toggle_block",
                data={"block_id": "A", "field": "briefing"})
    a = _load_block("A")
    assert a["skip_changeover"] is True and a["skip_briefing"] is True


def test_set_participants_override_and_clear(client):
    _seed_atomic_two_blocks()
    client.post("/events/plan_schedule/EDIT/set_block_participants",
                data={"block_id": "A", "participant_count_override": "42"})
    assert _load_block("A")["participant_count_override"] == 42
    client.post("/events/plan_schedule/EDIT/set_block_participants",
                data={"block_id": "A", "participant_count_override": ""})
    assert _load_block("A")["participant_count_override"] is None


def test_set_block_judge(client):
    _seed_atomic_two_blocks()
    client.post("/events/plan_schedule/EDIT/set_block_judge",
                data={"block_id": "A", "judge_id": "J7"})
    assert _load_block("A")["judge_id"] == "J7"


def test_add_final_block_and_grossring_render_and_persist(client):
    """Portal-Parity-Port 'Finale-Block + Grossring' (2026-10-29): Finalblock
    hinzufuegen -> Zeitplan-Seite rendert weiter 200, Teilnehmer-Override setzt
    die Dauer; Grossring-Checkbox am Ring persistiert auf event['grossring_rings']."""
    _seed_atomic_two_blocks()
    resp = client.post("/events/plan_schedule/EDIT/add_block",
                        data={"block_type": "final", "ring": "1", "title": "Finale"})
    assert resp.status_code == 302

    with open(os.path.join(_data_dir(), "events.json"), encoding="utf-8") as f:
        ev = json.load(f)[0]
    final_blocks = [b for b in ev["schedule"]["rings"]["1"]["blocks"] if b["type"] == "final"]
    assert len(final_blocks) == 1
    final_id = final_blocks[0]["id"]

    resp = client.post("/events/plan_schedule/EDIT/set_block_participants",
                        data={"block_id": final_id, "participant_count_override": "32"})
    assert resp.status_code == 302
    assert _load_block(final_id)["participant_count_override"] == 32

    resp = client.get("/events/plan_schedule/EDIT")
    assert resp.status_code == 200

    resp = client.post("/events/save_schedule/EDIT",
                        data={"start_time_ring_1": "08:00", "grossring_ring_1": "1"})
    assert resp.status_code == 302
    with open(os.path.join(_data_dir(), "events.json"), encoding="utf-8") as f:
        ev = json.load(f)[0]
    assert ev["grossring_rings"] == ["1"]

    resp = client.get("/events/plan_schedule/EDIT")
    assert resp.status_code == 200
    assert "Grossring".encode() in resp.data or "Grossring" in resp.get_data(as_text=True)


def _seed_live_event():
    ev = {
        "id": "LIVE",
        "name": "Live Smoke",
        "Datum": "2026-10-30",
        "num_rings": 1,
        "start_times_by_ring": {"ring_1": "08:00"},
        "runs": [{
            "id": "RL", "laufart": "Agility", "kategorie": "Large", "klasse": "2",
            "laufdaten": {"parcours_laenge": "150"},
            "entries": [
                {"Lizenznummer": "L1", "Startnummer": "101", "Hundename": "A", "Hundefuehrer": "HF1",
                 "zeit": "34.50", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
                {"Lizenznummer": "L2", "Startnummer": "102", "Hundename": "B", "Hundefuehrer": "HF2",
                 "zeit": "35.20", "fehler": "5", "verweigerungen": "0", "dis_abr": ""},
            ],
        }],
        "run_order": [],
        "schedule": {"schedule_version": 2, "event_id": "LIVE", "meta": {}, "rings": {"1": {
            "start_time": "08:00", "blocks": [
                {"id": "A", "type": "run", "timing_run_type": "agility", "size_category": "large",
                 "size_categories": [], "classes": ["2"], "judge_id": "", "title": "",
                 "sort_index": 0, "skip_changeover": False, "skip_briefing": False,
                 "force_new_group": False, "participant_count_override": None, "run_id": None},
            ]}}},
    }
    dd = _data_dir()
    with open(os.path.join(dd, "events.json"), "w", encoding="utf-8") as f:
        json.dump([ev], f, ensure_ascii=False, indent=2)
    with open(os.path.join(dd, "active_event.json"), "w", encoding="utf-8") as f:
        json.dump({"active_event_id": "LIVE"}, f)


@pytest.mark.parametrize("url", [
    "/ring_pc_dashboard/1",
    "/live/ranking/LIVE/RL",
    "/live/run_entry/LIVE/RL",
    "/ring_monitor/1",
    "/api/render_ring_monitor_content/1",
])
def test_live_routes_render_with_atomic_schedule(client, url):
    _seed_live_event()
    resp = client.get(url)
    assert resp.status_code == 200, f"{url} -> {resp.status_code}"
