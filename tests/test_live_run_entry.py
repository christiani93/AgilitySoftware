import json
import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
WEB_APP_DIR = os.path.join(ROOT_DIR, 'web_app')
if WEB_APP_DIR not in sys.path:
    sys.path.insert(0, WEB_APP_DIR)


def test_run_entry_sct_mct_display(client):
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

    os.makedirs('data', exist_ok=True)
    with open('data/events.json', 'w', encoding='utf8') as f:
        json.dump([event], f)

    resp = client.get('/live/run_entry/E1/R1')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "43" in html
    assert "60" in html
