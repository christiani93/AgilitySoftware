# app.py
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from flask_babel import Babel, gettext as _, lazy_gettext as _l
import sys
import importlib.metadata
import os
from datetime import datetime

from paths import bundle_dir, data_dir, resource_path

APP_VERSION = "4.4"
# Template-/Static-Ordner explizit auf das Bundle-Verzeichnis legen, damit
# PyInstaller-EXEs ihre eingebetteten Ressourcen finden.
app = Flask(
    __name__,
    template_folder=resource_path("templates"),
    static_folder=resource_path("static"),
)
from extensions import socketio
from flask_socketio import join_room
app.config['DATA_DIR'] = data_dir()
app.config['SOFTWARE_VERSION'] = APP_VERSION
app.config['SECRET_KEY'] = 'dein_super_geheimer_schluessel'
app.config['BABEL_DEFAULT_LOCALE'] = 'de'
app.config['BABEL_SUPPORTED_LOCALES'] = ['de', 'fr']
app.config['BABEL_TRANSLATION_DIRECTORIES'] = resource_path("translations")
babel = Babel()

def _select_locale():
    """Für /print/-Routen: Sprache aus den Einstellungen lesen. Sonst immer 'de'."""
    if request.path.startswith('/print/'):
        from utils import _load_settings
        return _load_settings().get('print_language', 'de')
    return 'de'

babel.init_app(app, locale_selector=_select_locale)
socketio.init_app(app)

# crashguard: Crash-/Fehler-Erfassung (URL+Token via CRASHGUARD_URL/_TOKEN env;
# ohne gesetzte Env nur lokales Schreiben, kein Versand).
try:
    import crashguard
    crashguard.install(project="AgilitySoftware",
                       repo_dir=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    crashguard.init_flask(app)
except Exception:
    pass

from utils import get_category_sort_key

def judge_name(judges, rid):
    try:
        key = str(rid)
    except Exception:
        key = rid
    try:
        for j in judges or []:
            if str(j.get('id')) == key:
                fn = (j.get('firstname') or "").strip()
                ln = (j.get('lastname') or "").strip()
                label = f"{fn} {ln}".strip()
                return label if label else key
    except Exception:
        pass
    return "N/A"


@app.template_filter('format_date')
def format_date(iso_date_string):
    if not iso_date_string: return ""
    try:
        dt_obj = datetime.fromisoformat(iso_date_string.replace('Z', '+00:00') if 'T' in iso_date_string else iso_date_string)
        return dt_obj.strftime('%d.%m.%Y')
    except (ValueError, TypeError): return iso_date_string

_SERVER_PORT = 5000  # wird beim Start aktualisiert


@app.context_processor
def inject_global_vars():
    return dict(python_version=sys.version,
        flask_version=importlib.metadata.version("flask"),
        software_version=APP_VERSION,
        server_lan_ips=_detect_lan_ips(),
        server_port=_SERVER_PORT,
        get_category_sort_key=get_category_sort_key, judge_name=judge_name)

@app.route('/')
def home():
    return render_template('home.html')


@app.route('/health')
def health():
    """Leichtgewichtiger Heartbeat-Endpoint für Ring-Server.

    Antwortet immer schnell und ohne Datei-/Settings-Zugriff."""
    return {'ok': True, 'service': 'AgilitySoftware', 'version': APP_VERSION}, 200

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    from utils import _load_settings, _save_data
    if request.method == 'POST':
        current_settings = _load_settings()
        current_settings['ranking_points'] = [int(p.strip()) for p in request.form.get('ranking_points', '').split(',') if p.strip().isdigit()]
        current_settings['time_per_starter'] = int(request.form.get('time_per_starter', 90))
        sct_factors = {'Jumping': {}, 'Agility': {}}
        for key, value in request.form.items():
            if key.startswith('sct_factor_') and value:
                parts = key.split('_')
                if len(parts) == 4: sct_factors.setdefault(parts[2], {})[parts[3]] = float(value)
        current_settings['sct_factors'] = sct_factors
        schema_template = {}
        for key, value in request.form.items():
            if key.startswith('schema_') and value.isdigit():
                schema_template[key.replace('schema_', '')] = int(value)
        current_settings['start_number_schema_template'] = schema_template
        # Portal-Sync-Einstellungen
        portal_url = request.form.get('portal_url', '').strip()
        current_settings['portal_url'] = portal_url
        current_settings['portal_live_api_key']    = request.form.get('portal_live_api_key', '').strip()
        current_settings['portal_results_api_key'] = request.form.get('portal_results_api_key', '').strip()
        current_settings['portal_device_id']       = request.form.get('portal_device_id', '').strip() or 'agility-software'
        # Drucksprache
        print_language = request.form.get('print_language', 'de')
        if print_language in ('de', 'fr'):
            current_settings['print_language'] = print_language
        _save_data('settings.json', current_settings)
        flash(_('Einstellungen erfolgreich gespeichert.'), 'success')
        return redirect(url_for('settings'))
    from portal_sync import get_sync_status
    return render_template('settings.html', settings=_load_settings(),
                           sync_status=get_sync_status())

@app.route('/settings/test-portal', methods=['POST'])
def settings_test_portal():
    from utils import _load_settings
    from portal_sync import test_portal_connection
    settings = _load_settings()
    result = test_portal_connection(settings)
    return jsonify(result)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error_page.html', title=_('Seite nicht gefunden'), message=_('Die angeforderte Seite existiert nicht.')), 404

@app.errorhandler(500)
def internal_server_error(e):
    import traceback
    print(f"Ein interner Serverfehler ist aufgetreten: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    return render_template('error_page.html', title=_('Serverfehler'), message=_('Auf dem Server ist ein interner Fehler aufgetreten.')), 500

def initialize_files():
    from utils import _save_data
    files = [
        'events.json', 'dogs.json', 'handlers.json', 'clubs.json', 'judges.json',
        'active_event.json', 'settings.json', 'snapshots.json', 'outbox.json'
    ]
    for filename in files:
        if not os.path.exists(os.path.join('data', filename)):
            _save_data(filename, [] if 'active' not in filename and 'settings' not in filename else {})

from blueprints.routes_events import events_bp
from blueprints.routes_master_data import master_data_bp
from blueprints.routes_print import print_bp
from blueprints.routes_live import live_bp
from blueprints.routes_debug import debug_bp
from blueprints.routes_sm import sm_bp
from blueprints.routes_skbs_sm import skbs_sm_bp
from blueprints.routes_bccs_sm import bccs_sm_bp
from blueprints.routes_fmbb import fmbb_bp

app.register_blueprint(events_bp)
app.register_blueprint(master_data_bp)
app.register_blueprint(live_bp)
app.register_blueprint(print_bp)
app.register_blueprint(debug_bp)
app.register_blueprint(sm_bp)
app.register_blueprint(skbs_sm_bp)
app.register_blueprint(bccs_sm_bp)
app.register_blueprint(fmbb_bp)

@app.context_processor
def inject_current_year():
    from datetime import datetime
    from utils import debug_tools_enabled
    return {"current_year": datetime.now().year,
            "debug_tools": debug_tools_enabled()}


@socketio.on('join_room')
def handle_join_room(data):
    room = (data or {}).get('room')
    if room:
        join_room(room)

def _detect_lan_ips():
    """Liefert eine Liste der LAN-IPv4-Adressen (primäre IP zuerst)."""
    import socket
    ips = []
    # Primäre LAN-IP via Dummy-Socket (zuverlässiger als gethostbyname)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    # Alle Interfaces als Fallback / Zusatz
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    return ips


def _print_startup_banner(port=5000):
    """Zeigt LAN-IP(s) prominent in der Konsole, damit der User sie in den
    Ring-Servern als Hauptserver-IP eintragen kann."""
    ips = _detect_lan_ips()

    print("")
    print("============================================================")
    print(f"  AgilitySoftware v{APP_VERSION}  -  HAUPTSERVER")
    print("============================================================")
    print(f"  Lokal:    http://127.0.0.1:{port}")
    if ips:
        for ip in ips:
            print(f"  LAN:      http://{ip}:{port}")
        print("")
        print(f"  >> Server-IP für Ring-Server (eintragen in AgilityRing): {ips[0]}")
    else:
        print("  LAN:      (keine externe IP gefunden)")
    print("============================================================")
    print("")


def _run_socketio(port=5000, debug=False):
    """Startet Flask-SocketIO. Wird im Hintergrund-Thread aufgerufen,
    wenn ein App-Fenster (pywebview) das Main-Thread besetzt."""
    try:
        socketio.run(app, host='0.0.0.0', port=port,
                     allow_unsafe_werkzeug=True, debug=debug)
    except TypeError:
        socketio.run(app, host='0.0.0.0', port=port, debug=debug)


def _open_app_window(port=5000):
    """Öffnet die App in einem nativen Fenster (Edge WebView2 via pywebview).

    Bricht still ab, wenn pywebview/WebView2 nicht verfügbar ist – dann
    läuft nur die Konsole und der User kann den Browser manuell öffnen.
    Deaktivieren via Env ``AGILITY_NO_WINDOW=1`` (Headless / NAS-Server).
    """
    if os.environ.get("AGILITY_NO_WINDOW"):
        return False
    try:
        import webview
    except ImportError:
        print("[INFO] pywebview nicht installiert – kein App-Fenster.")
        return False

    # Erst warten bis der Server lauscht (kurzer Probe-Loop), sonst lädt
    # WebView eine leere Seite.
    import socket as _socket, time as _time
    deadline = _time.time() + 5.0
    while _time.time() < deadline:
        with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            try:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            except OSError:
                pass
        _time.sleep(0.1)

    webview.create_window(
        f"AgilitySoftware v{APP_VERSION}",
        f"http://127.0.0.1:{port}",
        width=1280, height=900,
        resizable=True, confirm_close=False,
    )
    webview.start()  # blockiert bis Fenster geschlossen
    return True


if __name__ == '__main__':
    try:
        initialize_files()
        _print_startup_banner(port=5000)
        try:
            from updater import check_and_print
            check_and_print(APP_VERSION, component="AgilitySoftware")
        except Exception:
            pass

        debug_mode = not getattr(sys, "frozen", False)

        if os.environ.get("AGILITY_NO_WINDOW"):
            # Headless: Flask im Main-Thread (Standard-Verhalten)
            _run_socketio(port=5000, debug=debug_mode)
        else:
            # Fenster-Modus: Flask im Background, pywebview im Main-Thread
            import threading
            threading.Thread(target=_run_socketio,
                             kwargs={"port": 5000, "debug": False},
                             daemon=True).start()
            opened = _open_app_window(port=5000)
            if not opened:
                # Kein pywebview verfügbar – Server soll trotzdem laufen
                print("[INFO] Server läuft – im Browser http://127.0.0.1:5000 öffnen.")
                # Hauptthread aktiv halten
                import time
                while True:
                    time.sleep(3600)
            # Fenster wurde geschlossen → Prozess beenden
            os._exit(0)
    except Exception as _e:
        import traceback
        tb = traceback.format_exc()
        print("\n!! AgilitySoftware konnte nicht starten:")
        print(tb)
        if getattr(sys, "frozen", False):
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    0,
                    f"AgilitySoftware konnte nicht starten:\n\n{tb}",
                    "AgilitySoftware – Fehler",
                    0x10,  # MB_ICONERROR
                )
            except Exception:
                pass
        raise
