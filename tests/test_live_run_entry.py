import json
import os


def test_run_entry_sct_mct_display(client):
    """
    Integrationstest:
    - schreibt ein Testevent in data/events.json
    - ruft /live/run_entry/... auf
    - prüft, ob die gerundeten SCT/MCT im HTML auftauchen
    """

    data_dir = os.path.join(os.getcwd(), "data")
    os.makedirs(data_dir, exist_ok=True)

    events_path = os.path.join(data_dir, "events.json")

    event = {
        "id": "E1",
        "name": "Testevent",
        "runs": [{
            "id": "R1",
            "klasse": "2",
            "laufart": "Agility",
            "laufdaten": {"parcours_laenge": "150"},
            "entries": []
        }]
    }

    with open(events_path, "w", encoding="utf-8") as f:
        json.dump([event], f, indent=2, ensure_ascii=False)

    response = client.get("/live/run_entry/E1/R1")
    assert response.status_code == 200

    html = response.get_data(as_text=True)

    # SCT = ceil(150 / 3.5) = 43
    # MCT = ceil(150 / 2.5) = 60
    assert "43" in html
    assert "60" in html
