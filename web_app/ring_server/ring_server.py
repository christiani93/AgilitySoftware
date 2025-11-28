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
MAIN_SERVER_API = "http://127.0.0.1:5000/api/submit_result" 
port_num = 5001
app = Flask(__name__)

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
    "faults": 0, "refusals": 0
}

def reset_state():
    state.update(run_status="idle", active_run_id=None, current_starter=None, 
                 start_time_tod=None, faults=0, refusals=0)
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

if __name__ == '__main__':
    import argparse, os

    parser = argparse.ArgumentParser()
    parser.add_argument("--ring", dest="ring", default=None)
    parser.add_argument("--port", dest="port", type=int, default=None)
    # Fallback: Positionsargumente [ring_label] [port]
    parser.add_argument("pos_ring", nargs="?", default=None)
    parser.add_argument("pos_port", nargs="?", default=None)
    args, _unknown = parser.parse_known_args()

    ring_label = args.ring or args.pos_ring or os.environ.get("RING_LABEL") or "Ring 1"
    try:
        port_num = int(args.port or (args.pos_port if args.pos_port else 5001))
    except Exception:
        port_num = 5001

    # Für /config

    _RING_LABEL, _PORT_NUM = ring_label, port_num

    # State mit Ring befüllen
    state['ring_id'] = ring_label

    print(f"--- Ring-Server startet für '{ring_label}' auf Port {port_num} ---")

    # TIMY-Thread nur starten, wenn pywin32 vorhanden ist
    if TIMY_AVAILABLE:
        import threading
        def run_timy_listener():
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

        threading.Thread(target=run_timy_listener, daemon=True).start()
    else:
        print("!! TIMY nicht verfügbar (pywin32 fehlt) – Server läuft im 'ohne TIMY'-Modus.")

    # SocketIO/Flask starten – wichtig: port_num verwenden
    from flask_socketio import SocketIO
    try:
        socketio.run(app, host='127.0.0.1', port=port_num, allow_unsafe_werkzeug=True)
    except TypeError:
        # ältere Flask-SocketIO-Versionen haben allow_unsafe_werkzeug nicht
        socketio.run(app, host='127.0.0.1', port=port_num)

