import json
import os


def test_run_entry_sct_mct_display(client):
    """
    Integrationstest:
    - schreibt ein Testevent in data/events.json
    - ruft /live/run_entry/E1/R1 auf
    - prüft, ob die gerundeten SCT/MCT im HTML auftauchen
    """

    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)
    data_dir = os.path.join(project_root, "data")
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
            "entries": [
                {"lizenz": "A", "zeit": "34.50", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
                {"lizenz": "B", "zeit": "35.20", "fehler": "0", "verweigerungen": "0", "dis_abr": ""},
                {"lizenz": "C", "zeit": "32.00", "fehler": "5", "verweigerungen": "0", "dis_abr": ""},
                {"lizenz": "D", "zeit": "30.00", "fehler": "0", "verweigerungen": "0", "dis_abr": "DIS"},
            ]
        }]
    }

    with open(events_path, "w", encoding="utf-8") as f:
        json.dump([event], f, indent=2, ensure_ascii=False)

    response = client.get("/live/run_entry/E1/R1")
    assert response.status_code == 200

    html = response.get_data(as_text=True)

    # Erwartete gerundete Zeiten:
    # SCT = ceil(34.50 * 1.4) = 49
    # MCT = ceil(150 / 2.5) = 60
    assert "49" in html
    assert "60" in html
