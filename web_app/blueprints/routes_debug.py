# blueprints/routes_debug.py
import json
import os
import random
import math
import uuid

from flask import Blueprint, Response, redirect, url_for, flash, abort, request
from utils import _load_data, _save_data, _load_settings, _to_float, debug_tools_enabled

debug_bp = Blueprint('debug_bp', __name__)

# Routes, die NICHT vom Debug-Toggle betroffen sind (legitimer Export für Vergleich/Portal).
_DEBUG_GATE_EXEMPT = {'debug_bp.export_event_package'}


@debug_bp.before_request
def _gate_debug_tools():
    """Sperrt Debug-Generatoren/Test-Importe wenn ENABLE_DEBUG_TOOLS=0 (Produktion)."""
    if request.endpoint in _DEBUG_GATE_EXEMPT:
        return
    if not debug_tools_enabled():
        abort(404)


def _project_data_path(*parts) -> str:
    """Pfad innerhalb von web_app/data/..."""
    here = os.path.dirname(os.path.abspath(__file__))
    web_app = os.path.dirname(here)
    return os.path.join(web_app, 'data', *parts)




# ---------------------------------------------------------------------------
# Event-Package-Export als ZIP (für Portal-Import)
# ---------------------------------------------------------------------------

@debug_bp.route('/debug/export_event_package/<event_id>')
def export_event_package(event_id):
    """
    Lädt das angegebene Event als eventexport.v1.zip herunter.
    Diese Datei kann dann im Portal unter /admin/exchange/event-package/import
    hochgeladen werden — das Portal erstellt/aktualisiert das Event idempotent.
    """
    from portal_sync import build_event_export_zip

    events = _load_data('events.json')
    event = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        abort(404)

    zip_bytes = build_event_export_zip(event)
    from utils import _safe_http_filename
    safe_name = _safe_http_filename(event.get('Bezeichnung') or event_id)
    filename = f"eventexport_{safe_name}.zip"
    return Response(
        zip_bytes,
        mimetype='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
