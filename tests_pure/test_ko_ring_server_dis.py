"""
DIS am KO-Ring-Server (``ring_server.py``): im KO-System wird DIS GEZAEHLT,
nicht gesetzt -- jeder DIS = 5 Strafsekunden, mehrere pro Lauf moeglich. Anders
als der DIS-Button am normalen Ring-PC-Dashboard (der den TIMY-Lauf sofort
abschliesst) darf der laufende TIMY-Lauf dadurch NICHT unterbrochen werden, und
der Zaehler muss bis zum Speichern korrigierbar (runterzaehlbar) bleiben.

Treibt direkt die Modulfunktionen/-klassen von ``ring_server.py`` (keine
echte TIMY-Hardware oder laufende SocketIO-Server noetig -- ``TimyEvents``
ist eine reine Python-Klasse, ``socketio.emit`` laeuft ausserhalb eines
Request-Kontexts klaglos als No-Op-artiger Broadcast).
"""
import os
import sys

import pytest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
RING_SERVER_PATH = os.path.join(PROJECT_ROOT, "web_app", "ring_server")
WEB_APP_PATH = os.path.join(PROJECT_ROOT, "web_app")
for p in (WEB_APP_PATH, RING_SERVER_PATH):
    if p not in sys.path:
        sys.path.insert(0, p)

# Verhindert, dass der Testlauf eine echte timy_raw_*.log ins Repo schreibt
# (_RAW_LOG_ENABLED wird beim Modul-Import einmalig aus der Env gelesen).
os.environ.setdefault("TIMY_RAW_LOG_DISABLE", "1")

import ring_server as rs  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_and_capture(monkeypatch):
    """Frischer state vor jedem Test + Mitschnitt aller socketio.emit-Aufrufe."""
    rs.state.update(ring_id="TestRing", run_status="idle", active_run_id=None,
                     current_starter=None, start_time_tod=None,
                     faults=0, refusals=0, dis=0, final_time=None)
    emitted = []
    monkeypatch.setattr(rs.socketio, "emit", lambda event, *a, **kw: emitted.append((event, a, kw)))
    return emitted


def test_dis_defaults_zero_and_resets_zero(_reset_and_capture):
    assert rs.state["dis"] == 0
    rs.state["dis"] = 3
    rs.reset_state()
    assert rs.state["dis"] == 0


def test_count_dis_increments_without_touching_run_status(_reset_and_capture):
    rs.state["run_status"] = "running"
    rs.handle_count_dis({"value": 1})
    assert rs.state["dis"] == 1
    assert rs.state["run_status"] == "running"  # Lauf laeuft unbeeinflusst weiter


def test_multiple_dis_accumulate(_reset_and_capture):
    """Mehrere DIS pro Lauf moeglich -- der Zaehler summiert."""
    rs.state["run_status"] = "running"
    rs.handle_count_dis({"value": 1})
    rs.handle_count_dis({"value": 1})
    rs.handle_count_dis()  # default value=1
    assert rs.state["dis"] == 3


def test_count_dis_is_correctable_and_never_negative(_reset_and_capture):
    """Runterzaehlen korrigiert; unter 0 geht nicht."""
    rs.state["run_status"] = "running"
    rs.handle_count_dis({"value": 2})
    rs.handle_count_dis({"value": -1})
    assert rs.state["dis"] == 1
    rs.handle_count_dis({"value": -5})
    assert rs.state["dis"] == 0


def test_count_dis_ignored_when_idle(_reset_and_capture):
    """Ohne aktiven Lauf (idle) gibt es nichts zu zaehlen."""
    rs.state["run_status"] = "idle"
    rs.handle_count_dis({"value": 1})
    assert rs.state["dis"] == 0


def test_count_dis_allowed_after_run_finished(_reset_and_capture):
    """Nachkorrektur: DIS bleibt auch in 'finished_timing' noch zaehlbar."""
    rs.state["run_status"] = "finished_timing"
    rs.handle_count_dis({"value": 2})
    assert rs.state["dis"] == 2


def test_dis_survives_stop_impulse_and_lands_in_result_package(_reset_and_capture):
    """End-zu-Ende am TIMY-Impulspfad: C0 startet, DIS wird waehrend des
    laufenden Laufs gezaehlt (Lauf laeuft nachweislich weiter -- der Stopp-
    Impuls wird noch verarbeitet), C1 stoppt -- der emittierte
    result_package traegt die DIS-Anzahl."""
    events = rs.TimyEvents()
    rs.state["run_status"] = "ready"

    events.OnUSBInput("1 C0 10:00:00.00")
    assert rs.state["run_status"] == "running"

    rs.handle_count_dis({"value": 1})
    rs.handle_count_dis({"value": 1})
    assert rs.state["dis"] == 2
    assert rs.state["run_status"] == "running"  # DIS hat den Lauf NICHT gestoppt

    events.OnUSBInput("2 C1 10:00:05.00")

    finished = [a[0] for (ev, a, kw) in _reset_and_capture if ev == "run_finished_timing"]
    assert len(finished) == 1
    assert finished[0]["dis"] == 2
    assert finished[0]["final_time"] == "5.00"
