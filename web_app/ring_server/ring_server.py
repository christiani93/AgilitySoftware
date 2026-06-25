import argparse
# ring_server.py
import sys
import time
import requests
import re
import threading
from flask import Flask
from flask_socketio import SocketIO

try:
    import pythoncom
    import win32com.client
    TIMY_AVAILABLE = True
except ImportError:
    TIMY_AVAILABLE = False

# Hauptserver (AgilitySoftware). Kann überschrieben werden per
#   --server-ip / --server-port  (CLI)
#   MAIN_SERVER_IP / MAIN_SERVER_PORT  (Env)
# Default: lokaler Rechner.
MAIN_SERVER_IP = "127.0.0.1"
MAIN_SERVER_PORT = 5000
MAIN_SERVER_API = "http://127.0.0.1:5000/api/submit_result"

port_num = 5001
app = Flask(__name__)

# crashguard: web_app/ auf den Pfad legen, dann Crash-Erfassung aktivieren.
# URL+Token via CRASHGUARD_URL/_TOKEN env; ohne Env nur lokales Schreiben.
import os as _cg_os
sys.path.insert(0, _cg_os.path.dirname(_cg_os.path.dirname(_cg_os.path.abspath(__file__))))
try:
    import crashguard
    crashguard.install(project="AgilitySoftware-Ring",
                       repo_dir=_cg_os.path.dirname(sys.path[0]))
    crashguard.init_flask(app)
except Exception:
    pass

from flask import request

@app.after_request
def add_cors_headers(resp):
    # Erlaube lokale Zugriffe von 127.0.0.1:* und localhost
    resp.headers.setdefault('Access-Control-Allow-Origin', request.headers.get('Origin', '*'))
    resp.headers.setdefault('Access-Control-Allow-Credentials', 'true')
    resp.headers.setdefault('Access-Control-Allow-Headers', 'Content-Type, Authorization')
    resp.headers.setdefault('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    return resp

@app.route('/health')
def health():
    return {'ok': True}, 200

# Wird nach dem Parsen befüllt:
_RING_LABEL = None
_PORT_NUM = None

@app.route('/config')
def config():
    return {'ring': _RING_LABEL, 'port': _PORT_NUM}, 200
socketio = SocketIO(app, cors_allowed_origins="*") 

state = {
    "ring_id": None, "run_status": "idle", "active_run_id": None,
    "current_starter": None, "start_time_tod": None,
    "faults": 0, "refusals": 0,
    "final_time": None,
    # Hauptserver-Verbindungsstatus, wird vom Heartbeat-Thread aktualisiert
    "server_reachable": False,
    "server_last_check": 0.0,
}

def reset_state():
    state.update(run_status="idle", active_run_id=None, current_starter=None,
                 start_time_tod=None, faults=0, refusals=0, final_time=None)
    socketio.emit('state_update', state)
    print(f"[{state['ring_id']}] Zustand zurückgesetzt.")

def _time_str_to_seconds(time_str):
    if not time_str: return 0.0
    try:
        parts = time_str.split(':'); h, m = int(parts[0]), int(parts[1])
        s_parts = parts[2].split('.'); s = int(s_parts[0])
        frac_s = int(s_parts[1]) / (10**len(s_parts[1])) if len(s_parts) > 1 else 0
        return (h * 3600) + (m * 60) + s + frac_s
    except (ValueError, IndexError, TypeError): return 0.0

def parse_timy_output(line):
    impulse_match = re.match(r'^\s*(\d+)\s+(C\w+)\s+(\d{2}:\d{2}:\d{2}\.\d+)', line)
    if impulse_match: return {'type': 'impulse', 'channel': impulse_match.group(2), 'time_of_day': impulse_match.group(3)}
    return None

class TimyEvents:
    def OnConnectionOpen(self): print(f"[{state['ring_id']}] >> Verbindung zum Timy erfolgreich.")
    def OnUSBInput(self, data):
        line = data.strip()
        parsed = parse_timy_output(line)
        if not parsed: return

        print(f"[{state['ring_id']}] Impuls: {line} | Status: {state['run_status']}")

        if parsed['type'] == 'impulse':
            if parsed['channel'].startswith('C0') and state['run_status'] == 'ready':
                state.update(run_status='running', start_time_tod=parsed['time_of_day'])
                socketio.emit('start_clock')
                socketio.emit('state_update', state)

            elif parsed['channel'].startswith('C1') and state['run_status'] == 'running':
                stop_time_tod = parsed['time_of_day']
                start_s = _time_str_to_seconds(state['start_time_tod'])
                stop_s = _time_str_to_seconds(stop_time_tod)
                
                if start_s > 0 and stop_s > start_s:
                    final_time = stop_s - start_s
                    state['run_status'] = "finished_timing"
                    state['final_time'] = round(final_time, 2)

                    # KORREKTUR: Sendet das ganze Paket an den Ring-PC
                    result_package = {
                        'final_time': f"{final_time:.2f}",
                        'faults': state['faults'],
                        'refusals': state['refusals']
                    }
                    socketio.emit('run_finished_timing', result_package)
                    socketio.emit('state_update', state)
                else:
                    print("!! FEHLER: Ungültige Zeitberechnung. Status wird zurückgesetzt.")
                    reset_state()

@socketio.on('connect')
def handle_connect(): 
    print(f"[{state['ring_id']}] Client verbunden.")
    socketio.emit('state_update', state)

@socketio.on('set_starter_ready')
def handle_set_ready(data):
    if state['run_status'] in ['idle', 'finished_timing']:
        reset_state()
        state.update(run_status='ready', active_run_id=data.get('run_id'), current_starter=data.get('starter'))
        socketio.emit('state_update', state)
        print(f"[{state['ring_id']}] Starter bereit: {data.get('starter', {}).get('Startnummer')}")

@socketio.on('increment_counter')
def handle_increment(data):
    # KORREKTUR: Zählt Fehler/Verweigerung hoch
    if state['run_status'] == 'running' and data['type'] in ['faults', 'refusals']:
        state[data['type']] += data.get('value', 1)
        socketio.emit('state_update', state)
        print(f"[{state['ring_id']}] {data['type']} erhöht auf: {state[data['type']]}")

@socketio.on('reset_current_run')
def handle_reset(data=None):
    print(f"[{state['ring_id']}] Manueller Reset für aktuellen Lauf erhalten.")
    reset_state()

def run_timy_listener():
    global timy_usb_connection
    pythoncom.CoInitialize()
    try:
        timy_usb_connection = win32com.client.DispatchWithEvents('ALGEUSB.TimyUSB', TimyEvents)
        timy_usb_connection.Init()
        timy_usb_connection.OpenConnection(0)
        while True:
            pythoncom.PumpWaitingMessages()
            time.sleep(0.1)
    except Exception as e:
        print(f"!! TIMY-THREAD FEHLER: {e}")
    finally:
        if 'timy_usb_connection' in globals() and timy_usb_connection:
            timy_usb_connection.CloseConnection()
        pythoncom.CoUninitialize()

def _resolve_ring_config():
    """Liest Ring-Konfiguration aus CLI-Args, Env-Variablen und Defaults.

    Konvention: Port = 5000 + Ring-Nr (Ring 1 -> 5001, Ring 2 -> 5002, ...).
    Diese Konvention ist auch in der AgilitySoftware-Doku verankert.
    """
    import argparse, os

    parser = argparse.ArgumentParser()
    parser.add_argument("--ring", dest="ring", default=None,
                        help="Ring-Label, z.B. 'Ring 1'")
    parser.add_argument("--ring-number", dest="ring_number", type=int, default=None,
                        help="Ring-Nummer (1-9). Wenn gesetzt, wird daraus Label und Port abgeleitet.")
    parser.add_argument("--port", dest="port", type=int, default=None,
                        help="Port des Ring-Servers (Default: 5000 + Ring-Nr)")
    parser.add_argument("--server-ip", dest="server_ip", default=None,
                        help="IP des Hauptservers (AgilitySoftware)")
    parser.add_argument("--server-port", dest="server_port", type=int, default=None,
                        help="Port des Hauptservers (Default: 5000)")
    # Fallback: Positionsargumente [ring_label] [port]
    parser.add_argument("pos_ring", nargs="?", default=None)
    parser.add_argument("pos_port", nargs="?", default=None)
    args, _unknown = parser.parse_known_args()

    # Ring-Nummer ermitteln (für Port-Ableitung)
    ring_number = args.ring_number
    if ring_number is None:
        env_rn = os.environ.get("RING_NUMBER")
        if env_rn and env_rn.isdigit():
            ring_number = int(env_rn)

    # Ring-Label
    ring_label = args.ring or args.pos_ring or os.environ.get("RING_LABEL")
    if not ring_label and ring_number:
        ring_label = f"Ring {ring_number}"
    if not ring_label:
        ring_label = "Ring 1"
        ring_number = ring_number or 1

    # Ring-Nr aus Label ableiten falls noch unbekannt
    if ring_number is None:
        import re as _re
        m = _re.search(r"(\d+)", ring_label)
        ring_number = int(m.group(1)) if m else 1

    # Port: explizit > Env > 5000 + Ring-Nr
    try:
        port = int(args.port or (args.pos_port if args.pos_port else 0))
    except Exception:
        port = 0
    if not port:
        env_port = os.environ.get("RING_PORT")
        if env_port and env_port.isdigit():
            port = int(env_port)
    if not port:
        port = 5000 + int(ring_number)

    # Hauptserver-IP/Port
    server_ip = args.server_ip or os.environ.get("MAIN_SERVER_IP") or os.environ.get("SERVER_IP") or "127.0.0.1"
    try:
        server_port = int(args.server_port or os.environ.get("MAIN_SERVER_PORT") or 5000)
    except Exception:
        server_port = 5000

    return ring_label, ring_number, port, server_ip, server_port


def run_server(ring_label=None, ring_number=None, port_num=None,
               server_ip=None, server_port=None, with_dashboard=False):
    """Startet den Ring-Server. Wird sowohl vom CLI-Entry als auch vom
    Tkinter-Launcher aufgerufen. Fehlende Werte werden aus CLI/Env aufgelöst.

    Args:
        with_dashboard: Wenn True, läuft SocketIO im Hintergrund-Thread und
            ein Tk-Live-Status-Fenster im Main-Thread (für die Ring-EXE).
            Wenn False (Default), wird socketio.run blockierend im Main-Thread
            ausgeführt (CLI-/Headless-Modus).
    """
    global _RING_LABEL, _PORT_NUM

    cfg_label, cfg_number, cfg_port, cfg_server_ip, cfg_server_port = _resolve_ring_config()
    ring_label = ring_label or cfg_label
    ring_number = ring_number if ring_number is not None else cfg_number
    port_num = port_num or cfg_port
    server_ip = server_ip or cfg_server_ip
    server_port = server_port or cfg_server_port

    # Hauptserver-Endpoint aktualisieren (Modul-globals überschreiben)
    globals()["MAIN_SERVER_IP"] = server_ip
    globals()["MAIN_SERVER_PORT"] = server_port
    globals()["MAIN_SERVER_API"] = f"http://{server_ip}:{server_port}/api/submit_result"

    _RING_LABEL, _PORT_NUM = ring_label, port_num
    state['ring_id'] = ring_label

    print("============================================")
    print(f"  Ring-Server '{ring_label}' (Nr. {ring_number})")
    print(f"  Listen-Port:    {port_num}")
    print(f"  Hauptserver:    http://{server_ip}:{server_port}")
    print(f"  TIMY verfügbar: {TIMY_AVAILABLE}")
    print("============================================")

    # Heartbeat zum Hauptserver – aktualisiert state['server_reachable'].
    import threading as _threading

    def _heartbeat_thread():
        import time as _t
        import requests as _rq
        url = f"http://{server_ip}:{server_port}/health"
        while True:
            ok = False
            try:
                r = _rq.get(url, timeout=2.0)
                ok = (r.status_code == 200)
            except Exception:
                ok = False
            state["server_reachable"] = ok
            state["server_last_check"] = _t.time()
            _t.sleep(3.0)

    _threading.Thread(target=_heartbeat_thread, daemon=True).start()

    if TIMY_AVAILABLE:
        import threading
        def _timy_thread():
            try:
                pythoncom.CoInitialize()
                try:
                    timy = win32com.client.DispatchWithEvents('ALGEUSB.TimyUSB', TimyEvents)
                    timy.Init()
                    timy.OpenConnection(0)
                    import time
                    while True:
                        pythoncom.PumpWaitingMessages()
                        time.sleep(0.1)
                finally:
                    try:
                        timy.CloseConnection()
                    except Exception:
                        pass
                    pythoncom.CoUninitialize()
            except Exception as e:
                print(f"!! TIMY-THREAD FEHLER: {e}")

        threading.Thread(target=_timy_thread, daemon=True).start()
    else:
        print("!! TIMY nicht verfügbar (pywin32 fehlt) – Server läuft im 'ohne TIMY'-Modus.")

    def _run_socketio():
        try:
            socketio.run(app, host='127.0.0.1', port=port_num, allow_unsafe_werkzeug=True)
        except TypeError:
            socketio.run(app, host='127.0.0.1', port=port_num)

    if with_dashboard:
        # SocketIO im Hintergrund, Tk-Dashboard im Main-Thread.
        import threading
        threading.Thread(target=_run_socketio, daemon=True).start()

        try:
            from ring_dashboard import RingDashboard
        except ImportError:
            import os as _os, sys as _sys
            _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
            from ring_dashboard import RingDashboard

        dash = RingDashboard(
            state_ref=state,
            ring_label=ring_label,
            ring_number=ring_number,
            listen_port=port_num,
            server_ip=server_ip,
            server_port=server_port,
            timy_available=TIMY_AVAILABLE,
        )
        dash.run()
    else:
        _run_socketio()


if __name__ == '__main__':
    run_server()

