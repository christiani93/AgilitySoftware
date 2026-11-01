"""
Software-Export der KO-Cup-Final-Sieger (Halloween-Cup) → Titelverteidiger-Automatik.

`_build_cup_finals_payload` baut aus `event['ko_cup']['finals']` das persistente
`cup_finals.json`-Paket (Lizenz + final_rank je Kategorie), und `build_result_export_zip`
legt es ins resultexport-ZIP. Pendant zur Portal-Ingestion (import_result_export_zip).
"""
import io
import json
import zipfile

import portal_sync as ps


def _ko_event():
    return {
        "id": "EV1", "Datum": "31.10.2026",
        "ko_cup": {"enabled": True, "finals": [
            {"id": "f1", "category_code": "Large", "class_level": None,
             "group_label": "Large", "is_published": False,
             "participants": [
                 {"id": "p1", "license_no": "14554", "dog_name": "Youri",
                  "handler_name": "Roland Marro", "draw_number": 18, "seeding_rank": 1, "source": "run"},
                 {"id": "p2", "license_no": "15709", "dog_name": "Feivel",
                  "handler_name": "Nadine Gass", "draw_number": 5, "seeding_rank": 2, "source": "run"}],
             "results": [{"participant_id": "p1", "rank": 1}, {"participant_id": "p2", "rank": 2}]},
        ]},
    }


def test_payload_maps_winner_license_and_rank():
    pl = ps._build_cup_finals_payload(_ko_event())
    assert pl["cup_ruleset"] == "halloween_cup"
    assert pl["season"] == 2026
    assert len(pl["finals"]) == 1
    f = pl["finals"][0]
    assert f["category_code"] == "Large"
    winner = next(r for r in f["results"] if r["final_rank"] == 1)
    assert winner["license"] == "14554"
    assert winner["dog_name"] == "Youri"


def test_season_falls_back_to_current_year(monkeypatch):
    ev = _ko_event()
    ev.pop("Datum")
    import datetime
    pl = ps._build_cup_finals_payload(ev)
    assert pl["season"] == datetime.date.today().year


def test_no_payload_without_ko_cup():
    assert ps._build_cup_finals_payload({"id": "x"}) is None


def test_no_payload_without_results():
    ev = {"ko_cup": {"finals": [{"participants": [], "results": []}]}}
    assert ps._build_cup_finals_payload(ev) is None


def test_cup_ruleset_overridable():
    ev = _ko_event()
    ev["cup_ruleset"] = "spring_cup"
    assert ps._build_cup_finals_payload(ev)["cup_ruleset"] == "spring_cup"


def test_zip_contains_cup_finals_json():
    zip_bytes = ps.build_result_export_zip(_ko_event(), final=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert "cup_finals.json" in zf.namelist()
        data = json.loads(zf.read("cup_finals.json"))
    assert data["finals"][0]["results"][0]["license"] == "14554"
