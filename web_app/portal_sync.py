"""
portal_sync.py — Synchronisation AgilitySoftware → AgilityPortal

Schnittstellen:
  POST {portal_url}/api/liveupdate   → push_live_update()
  POST {portal_url}/api/resultexport → send_result_export()

Format Live-Update: agility.exchange.liveupdate.v1
Format Ergebnis-Export: agility.exchange.resultexport.v1
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from threading import Thread
from typing import Optional

# ----------------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(v, default=0) -> int:
    try:
        return int(v or 0)
    except (ValueError, TypeError):
        return default


def _safe_float(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


# Laufender Sequenz-Counter (pro Prozess-Session)
_seq_counter = 0


def _next_seq() -> int:
    global _seq_counter
    _seq_counter += 1
    return _seq_counter


# ----------------------------------------------------------------------------
# Live-Update Push
# ----------------------------------------------------------------------------

def _build_live_update_payload(event: dict, run: dict, result_entry: dict,
                                device_id: str) -> dict:
    """Erzeugt das Payload für einen einzelnen Live-Update."""
    entry_result = result_entry.get("result") or {}
    return {
        "schema":             "agility.exchange.liveupdate.v1",
        "event_external_id":  event.get("external_id") or event.get("id") or "",
        "source": {
            "system":  "agility-software",
            "version": "4.4",
            "device":  device_id or "agility-software",
        },
        "sequence_no": _next_seq(),
        "sent_at":     _utc_now_iso(),
        # Lauf-Kontext
        "run_id":       run.get("id"),
        "run_name":     run.get("name") or run.get("title") or "",
        "ring":         run.get("assigned_ring") or run.get("ring") or "Ring 1",
        "discipline":   run.get("laufart") or run.get("discipline") or "",
        "category_code":run.get("kategorie") or run.get("category") or "",
        "class_level":  _safe_int(run.get("klasse") or run.get("class_level")),
        # Ergebnis
        "result": {
            "license_no":      result_entry.get("Lizenznummer") or "",
            "dog_name":        result_entry.get("Hundename") or "",
            "handler_name":    result_entry.get("Hundefuehrer") or "",
            "start_no":        _safe_int(result_entry.get("Startnummer")),
            "zeit":            _safe_float(entry_result.get("zeit")),
            "fehler":          _safe_int(entry_result.get("fehler")),
            "verweigerungen":  _safe_int(entry_result.get("verweigerungen")),
            "disqualifikation":entry_result.get("disqualifikation"),
            "platz":           result_entry.get("platz"),
            "qualifikation":   result_entry.get("qualifikation"),
            "fehler_total":    _safe_float(result_entry.get("fehler_total")),
            "zeit_total":      _safe_float(result_entry.get("zeit_total")),
        },
    }


def _do_push_live_update(url: str, api_key: str, payload: dict) -> None:
    """Sendet das Live-Update an das Portal (blocking, läuft in Background-Thread)."""
    try:
        import urllib.request
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Api-Key":    api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            pass  # Fire-and-forget
    except Exception as exc:
        # Nie den Hauptprozess blockieren
        try:
            import sys
            print(f"[portal_sync] Live-Update fehlgeschlagen: {exc}", file=sys.stderr)
        except Exception:
            pass


def push_live_update(settings: dict, event: dict, run: dict,
                     result_entry: dict) -> None:
    """
    Schickt einen Live-Update asynchron (Background-Thread) an das Portal.
    Tut nichts, wenn portal_url oder portal_live_api_key nicht konfiguriert sind.
    """
    portal_url = (settings.get("portal_url") or "").rstrip("/")
    api_key    = settings.get("portal_live_api_key") or ""
    device_id  = settings.get("portal_device_id") or "agility-software"

    if not portal_url or not api_key:
        return

    endpoint = f"{portal_url}/api/liveupdate"
    payload  = _build_live_update_payload(event, run, result_entry, device_id)

    t = Thread(target=_do_push_live_update, args=(endpoint, api_key, payload), daemon=True)
    t.start()


# ----------------------------------------------------------------------------
# Result-Export ZIP
# ----------------------------------------------------------------------------

def build_result_export_zip(event: dict, final: bool = False) -> bytes:
    """
    Erzeugt ein agility.exchange.resultexport.v1 ZIP im Arbeitsspeicher.

    Jeder Lauf (run) im Event wird als eigene Klasse exportiert.
    Nur Entries mit gespeichertem Ergebnis werden inkludiert.
    """
    try:
        from utils import _calculate_run_results, _load_settings
        settings = _load_settings()
    except Exception:
        settings = {}

    event_external_id = event.get("external_id") or event.get("id") or ""

    classes = []
    for run in event.get("runs") or []:
        run_id_for_log = run.get("id") or ""
        try:
            results_all = _calculate_run_results(run, settings)
        except Exception:
            results_all = []

        rows = []
        for entry in results_all:
            entry_result = entry.get("result") or {}
            # Nur Entries mit Ergebnis
            if not entry_result.get("zeit") and not entry_result.get("disqualifikation"):
                continue

            disq = entry_result.get("disqualifikation")
            eliminated = disq in ("DIS", "ABR")
            dns        = disq == "DNS"
            status     = entry.get("qualifikation") or ("DNS" if dns else ("DIS" if disq else "NB"))
            rows.append({
                "registration_external_id": entry.get("external_id") or entry.get("Lizenznummer") or "",
                "start_no":    _safe_int(entry.get("Startnummer")),
                "rank":        entry.get("platz"),
                "time_s":      _safe_float(entry.get("zeit_total")),
                "faults":      _safe_int(entry_result.get("fehler")),
                "refusals":    _safe_int(entry_result.get("verweigerungen")),
                "eliminated":  eliminated,
                "status":      status,
                "dog_name":    entry.get("Hundename") or "",
                "handler_name":entry.get("Hundefuehrer") or "",
            })

        if not rows:
            continue  # Lauf ohne Ergebnisse überspringen

        classes.append({
            "ring":          run.get("assigned_ring") or run.get("ring") or "Ring 1",
            "discipline":    run.get("laufart") or run.get("discipline") or "",
            "category_code": run.get("kategorie") or run.get("category") or "",
            "class_level":   _safe_int(run.get("klasse") or run.get("class_level")),
            "run_no":        1,
            "results":       rows,
        })

    results_payload = {
        "event_external_id": event_external_id,
        "exported_at":       _utc_now_iso(),
        "final":             bool(final),
        "classes":           classes,
        "documents":         [],
    }
    manifest = {"schema": "agility.exchange.resultexport.v1", "generated_at": _utc_now_iso()}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        zf.writestr("results.json",  json.dumps(results_payload, ensure_ascii=False))
    return buf.getvalue()


def _do_send_result_export(url: str, api_key: str, zip_bytes: bytes) -> dict:
    """Sendet den Result-Export an das Portal (blocking)."""
    try:
        import urllib.request
        boundary = b"----AgilitySoftwareBoundary"
        body = (
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="file"; filename="result_export.zip"\r\n'
            b"Content-Type: application/zip\r\n\r\n"
            + zip_bytes
            + b"\r\n--" + boundary + b"--\r\n"
        )
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary.decode()}",
                "X-Api-Key":    api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"error": str(exc)}


def send_result_export(settings: dict, event: dict, final: bool = False) -> dict:
    """
    Erzeugt den Result-Export ZIP und sendet ihn ans Portal.
    Gibt das JSON-Response-Dict zurück (oder {"error": ...} bei Fehler).
    Blockierend (für manuellen Export via UI).
    """
    portal_url = (settings.get("portal_url") or "").rstrip("/")
    api_key    = settings.get("portal_results_api_key") or ""

    if not portal_url or not api_key:
        return {"error": "portal_url oder portal_results_api_key nicht konfiguriert"}

    zip_bytes = build_result_export_zip(event, final=final)
    endpoint  = f"{portal_url}/api/resultexport"
    return _do_send_result_export(endpoint, api_key, zip_bytes)
