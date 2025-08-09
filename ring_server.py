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
except ImportError:
    sys.exit("Fehler: Das Paket 'pywin32' wird für die Timy-Kommunikation benötigt.")

MAIN_SERVER_API = "http://127.0.0.1:5000/api/submit_result" 
RING_SERVER_PORT = 5001
app = Flask(__name__)
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
def handle_reset(data):
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
    if len(sys.argv) > 1:
        state['ring_id'] = sys.argv[1]
    else:
        sys.exit("!! FEHLER: Keine Ring-ID übergeben. Beispiel: python ring_server.py \"Ring 1\"")
    
    print(f"--- Starte Ring-Server für '{state['ring_id']}' auf Port {RING_SERVER_PORT} ---")
    
    timy_thread = threading.Thread(target=run_timy_listener, daemon=True)
    timy_thread.start()
    
    socketio.run(app, host='127.0.0.1', port=RING_SERVER_PORT, allow_unsafe_werkzeug=True)
