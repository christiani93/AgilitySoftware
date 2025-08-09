# app.py
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from flask_socketio import SocketIO
import sys
import flask as flask_module
import os
from datetime import datetime

APP_VERSION = "4.3"
app = Flask(__name__)
app.config['SECRET_KEY'] = 'dein_super_geheimer_schluessel'
socketio = SocketIO(app)

from utils import get_category_sort_key

@app.template_filter('format_date')
def format_date(iso_date_string):
    if not iso_date_string: return ""
    try:
        dt_obj = datetime.fromisoformat(iso_date_string.replace('Z', '+00:00') if 'T' in iso_date_string else iso_date_string)
        return dt_obj.strftime('%d.%m.%Y')
    except (ValueError, TypeError): return iso_date_string

@app.context_processor
def inject_global_vars():
    return dict(python_version=sys.version, flask_version=flask_module.__version__, get_category_sort_key=get_category_sort_key)

@app.route('/')
def home():
    return render_template('home.html')

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
        _save_data('settings.json', current_settings)
        flash('Einstellungen erfolgreich gespeichert.', 'success')
        return redirect(url_for('settings'))
    return render_template('settings.html', settings=_load_settings())

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error_page.html', title='Seite nicht gefunden', message='Die angeforderte Seite existiert nicht.'), 404

@app.errorhandler(500)
def internal_server_error(e):
    import traceback
    print(f"Ein interner Serverfehler ist aufgetreten: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    return render_template('error_page.html', title='Serverfehler', message='Auf dem Server ist ein interner Fehler aufgetreten.'), 500

def initialize_files():
    from utils import _save_data
    files = ['events.json', 'dogs.json', 'handlers.json', 'clubs.json', 'judges.json', 'active_event.json', 'settings.json']
    for filename in files:
        if not os.path.exists(os.path.join('data', filename)):
            _save_data(filename, [] if 'active' not in filename and 'settings' not in filename else {})

from blueprints.routes_events import events_bp
from blueprints.routes_master_data import master_data_bp
from blueprints.routes_print import print_bp
from blueprints.routes_live import live_bp
from blueprints.routes_debug import debug_bp

app.register_blueprint(events_bp)
app.register_blueprint(master_data_bp)
app.register_blueprint(live_bp)
app.register_blueprint(print_bp)
app.register_blueprint(debug_bp)

if __name__ == '__main__':
    initialize_files()
    socketio.run(app, host='0.0.0.0', allow_unsafe_werkzeug=True, debug=True)
