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
# Sync-Status (in-memory + persistiert in data/portal_sync_status.json)
# ----------------------------------------------------------------------------

_sync_status: dict = {
    "live_update":     {"last_at": None, "last_ok": None, "last_error": None, "count_ok": 0, "count_err": 0},
    "result_export":   {"last_at": None, "last_ok": None, "last_error": None, "count_ok": 0, "count_err": 0},
}

STATUS_FILE = "portal_sync_status.json"


def _load_sync_status() -> dict:
    global _sync_status
    try:
        from utils import _load_data
        data = _load_data(STATUS_FILE)
        if isinstance(data, dict) and "live_update" in data:
            _sync_status = data
    except Exception:
        pass
    return _sync_status


def _save_sync_status() -> None:
    try:
        from utils import _save_data
        _save_data(STATUS_FILE, _sync_status)
    except Exception:
        pass


def _record_status(key: str, ok: bool, error: str | None = None) -> None:
    global _sync_status
    _load_sync_status()
    entry = _sync_status.setdefault(key, {"last_at": None, "last_ok": None, "last_error": None, "count_ok": 0, "count_err": 0})
    entry["last_at"] = _utc_now_iso()
    if ok:
        entry["last_ok"]    = entry["last_at"]
        entry["last_error"] = None
        entry["count_ok"]   = entry.get("count_ok", 0) + 1
    else:
        entry["last_error"] = error or "Unbekannter Fehler"
        entry["count_err"]  = entry.get("count_err", 0) + 1
    _save_sync_status()


def get_sync_status() -> dict:
    return _load_sync_status()


# ----------------------------------------------------------------------------
# Verbindungstest
# ----------------------------------------------------------------------------

def test_portal_connection(settings: dict) -> dict:
    """
    Testet die Verbindung zum Portal.
    Gibt {"live": True/False, "results": True/False, "errors": {...}} zurück.
    """
    import urllib.request
    portal_url = (settings.get("portal_url") or "").rstrip("/")
    live_key   = settings.get("portal_live_api_key") or ""
    res_key    = settings.get("portal_results_api_key") or ""

    results = {"portal_url": portal_url, "live": None, "results": None, "errors": {}}

    if not portal_url:
        results["errors"]["general"] = "Keine Portal-URL konfiguriert"
        return results

    # Test Live-Update API mit Minimal-Payload (wird abgelehnt wegen falschem Schema,
    # aber ein 400 statt 403/000 beweist, dass die Verbindung steht und der Key korrekt ist)
    if live_key:
        try:
            test_payload = json.dumps({
                "schema": "agility.exchange.liveupdate.v1",
                "event_external_id": "test-connection",
                "source": {"device": settings.get("portal_device_id") or "agility-software"},
                "sequence_no": 0,
                "sent_at": _utc_now_iso(),
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{portal_url}/api/liveupdate",
                data=test_payload,
                headers={"Content-Type": "application/json", "X-Api-Key": live_key},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                results["live"] = True  # 200 OK
        except Exception as exc:
            code = getattr(getattr(exc, "code", None), "__int__", lambda: None)() or getattr(exc, "code", None)
            if code == 403:
                results["live"]   = False
                results["errors"]["live"] = "API-Key ungültig (403)"
            elif code in (200, 400):
                results["live"] = True  # 400 = connected, key ok, payload rejected
            else:
                results["live"]   = False
                results["errors"]["live"] = str(exc)
    else:
        results["errors"]["live"] = "Kein Live-API-Key konfiguriert"

    # Test Results API mit leerem ZIP
    if res_key:
        try:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("manifest.json", json.dumps({"schema": "agility.exchange.resultexport.v1"}))
                zf.writestr("results.json", json.dumps({
                    "event_external_id": "test-connection",
                    "exported_at": _utc_now_iso(),
                    "final": False, "classes": [], "documents": [],
                }))
            zip_bytes = buf.getvalue()
            boundary = b"----TestBoundary"
            body = (b"--" + boundary + b"\r\n"
                    b'Content-Disposition: form-data; name="file"; filename="test.zip"\r\n'
                    b"Content-Type: application/zip\r\n\r\n"
                    + zip_bytes + b"\r\n--" + boundary + b"--\r\n")
            req = urllib.request.Request(
                f"{portal_url}/api/resultexport",
                data=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary.decode()}",
                    "X-Api-Key": res_key,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                results["results"] = True
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code == 403:
                results["results"] = False
                results["errors"]["results"] = "API-Key ungültig (403)"
            elif code in (200, 400):
                results["results"] = True
            else:
                results["results"] = False
                results["errors"]["results"] = str(exc)
    else:
        results["errors"]["results"] = "Kein Results-API-Key konfiguriert"

    return results

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


# Sequenz-Counter: Timestamp-Basis (ms) + lokaler Zähler → überlebt Neustarts eindeutig
import time as _time
_seq_counter = 0
_seq_base = int(_time.time() * 1000)  # fester Offset pro Prozess-Session


def _next_seq() -> int:
    global _seq_counter
    _seq_counter += 1
    return _seq_base + _seq_counter


# ----------------------------------------------------------------------------
# Live-Update Push
# ----------------------------------------------------------------------------

def _starter_brief(entry: dict) -> dict:
    """Kompakter Starter-Dict für das Portal."""
    return {
        "start_no":    _safe_int(entry.get("Startnummer")),
        "dog_name":    entry.get("Hundename") or "",
        "handler_name":entry.get("Hundefuehrer") or "",
        "license_no":  entry.get("Lizenznummer") or "",
        "is_in_season":bool(entry.get("is_in_season")),
    }


def _build_startlist_snapshot(run: dict) -> dict:
    """
    Gibt den aktuellen Startlisten-Stand zurück:
    - current_starter: wer gerade läuft
    - next_starter:    wer als nächstes kommt
    - remaining:       alle noch nicht gestarteten Starter (inkl. current)
    """
    entries = run.get("entries") or []
    # Sortiert nach Startnummer
    sorted_entries = sorted(entries, key=lambda e: _safe_int(e.get("Startnummer"), 99999))

    def _has_result(e):
        r = e.get("result") or {}
        return bool(r.get("zeit") or r.get("disqualifikation"))

    remaining = [e for e in sorted_entries if not _has_result(e)]

    current = run.get("current_starter") or (remaining[0] if remaining else {})
    nxt     = run.get("next_starter")    or (remaining[1] if len(remaining) > 1 else {})

    return {
        "current_starter": _starter_brief(current) if current else None,
        "next_starter":    _starter_brief(nxt)     if nxt     else None,
        "remaining_count": len(remaining),
        "remaining":       [_starter_brief(e) for e in remaining],
    }


def _normalize_ring(raw: str) -> str:
    """Normalisiert Ring-Bezeichnungen: 'ring_1', '1', 'ring1' → 'Ring 1'."""
    import re
    if not raw:
        return "Ring 1"
    m = re.search(r'\d+', str(raw))
    return f"Ring {m.group()}" if m else str(raw)


def _build_live_update_payload(event: dict, run: dict, result_entry: dict,
                                device_id: str, update_type: str = "result") -> dict:
    """Erzeugt das Payload für einen Live-Update (Ergebnis oder Lauf-Wechsel)."""
    entry_result = result_entry.get("result") or {} if result_entry else {}
    startlist    = _build_startlist_snapshot(run)

    payload = {
        "schema":             "agility.exchange.liveupdate.v1",
        "event_external_id":  event.get("external_id") or event.get("id") or "",
        "source": {
            "system":  "agility-software",
            "version": "4.4",
            "device":  device_id or "agility-software",
        },
        "sequence_no":  _next_seq(),
        "sent_at":      _utc_now_iso(),
        "update_type":  update_type,   # "result" | "run_changed"
        # Lauf-Kontext
        "run_id":        run.get("id"),
        "run_name":      run.get("name") or run.get("title") or "",
        "ring":          _normalize_ring(run.get("assigned_ring") or run.get("ring")),
        "discipline":    run.get("laufart") or run.get("discipline") or "",
        "category_code": run.get("kategorie") or run.get("category") or "",
        "class_level":   _safe_int(run.get("klasse") or run.get("class_level")),
        # Aktuelle Startliste
        "startlist":     startlist,
    }

    if result_entry:
        payload["result"] = {
            "license_no":       result_entry.get("Lizenznummer") or "",
            "dog_name":         result_entry.get("Hundename") or "",
            "handler_name":     result_entry.get("Hundefuehrer") or "",
            "start_no":         _safe_int(result_entry.get("Startnummer")),
            "zeit":             _safe_float(entry_result.get("zeit")),
            "fehler":           _safe_int(entry_result.get("fehler")),
            "verweigerungen":   _safe_int(entry_result.get("verweigerungen")),
            "disqualifikation": entry_result.get("disqualifikation"),
            "platz":            result_entry.get("platz"),
            "qualifikation":    result_entry.get("qualifikation"),
            "fehler_total":     _safe_float(result_entry.get("fehler_total")),
            "zeit_total":       _safe_float(result_entry.get("zeit_total")),
        }

    return payload


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
            _record_status("live_update", ok=True)
    except Exception as exc:
        _record_status("live_update", ok=False, error=str(exc))
        try:
            import sys
            print(f"[portal_sync] Live-Update fehlgeschlagen: {exc}", file=sys.stderr)
        except Exception:
            pass


def push_live_update(settings: dict, event: dict, run: dict,
                     result_entry: dict) -> None:
    """Schickt einen Ergebnis-Live-Update asynchron ans Portal."""
    portal_url = (settings.get("portal_url") or "").rstrip("/")
    api_key    = settings.get("portal_live_api_key") or ""
    device_id  = settings.get("portal_device_id") or "agility-software"

    if not portal_url or not api_key:
        return

    endpoint = f"{portal_url}/api/liveupdate"
    payload  = _build_live_update_payload(event, run, result_entry, device_id, update_type="result")

    t = Thread(target=_do_push_live_update, args=(endpoint, api_key, payload), daemon=True)
    t.start()


def push_run_changed(settings: dict, event: dict, run: dict) -> None:
    """Schickt einen Lauf-Wechsel-Update asynchron ans Portal (kein Ergebnis, nur Startliste)."""
    portal_url = (settings.get("portal_url") or "").rstrip("/")
    api_key    = settings.get("portal_live_api_key") or ""
    device_id  = settings.get("portal_device_id") or "agility-software"

    if not portal_url or not api_key:
        return

    endpoint = f"{portal_url}/api/liveupdate"
    payload  = _build_live_update_payload(event, run, None, device_id, update_type="run_changed")

    t = Thread(target=_do_push_live_update, args=(endpoint, api_key, payload), daemon=True)
    t.start()


# ----------------------------------------------------------------------------
# Result-Export ZIP
# ----------------------------------------------------------------------------

def build_event_export_zip(event: dict) -> bytes:
    """
    Erzeugt ein agility.exchange.eventexport.v1 ZIP aus einem Software-Event-Dict.
    Inverse von Portal's build_event_export_zip — symmetrisch, gleiches Schema.

    ZIP-Inhalt:
      - manifest.json
      - event.json      (external_id, name, location, starts_at, ends_at, billing_mode)
      - entities.json   (persons[], dogs[])
      - registrations.json
      - start_numbers.json
      - schedule.json

    Verwendet `external_id`, `Lizenznummer` etc. aus dem Software-Event-Dict.
    Hund-external_id = Lizenznummer (eindeutig im Software-Modell).
    Person-external_id = "p_" + lower(nachname + vorname) (stabil).
    """
    import hashlib as _hashlib

    event_external_id = event.get("external_id") or event.get("id") or ""

    persons: dict[str, dict] = {}
    dogs: dict[str, dict] = {}
    registrations: list[dict] = []
    seen_reg: set[tuple] = set()

    # Erst Startnummern sammeln (pro Lizenz die kleinste aus allen Runs),
    # damit wir sie direkt in jede Registration einsetzen koennen
    start_no_by_lic: dict[str, int] = {}
    for run in event.get("runs") or []:
        for entry in run.get("entries") or []:
            lic = (entry.get("Lizenznummer") or "").strip()
            snr = _safe_int(entry.get("startnummer_offiziell") or entry.get("Startnummer"), 0)
            if lic and snr > 0:
                cur = start_no_by_lic.get(lic)
                if cur is None or snr < cur:
                    start_no_by_lic[lic] = snr

    for run in event.get("runs") or []:
        kategorie = run.get("kategorie") or ""
        klasse_raw = run.get("klasse")
        try:
            klasse = int(klasse_raw) if klasse_raw is not None else None
        except (ValueError, TypeError):
            klasse = None
        for entry in run.get("entries") or []:
            lic = (entry.get("Lizenznummer") or "").strip()
            if not lic:
                continue
            vorname = (entry.get("Vorname") or "").strip()
            nachname = (entry.get("Nachname") or "").strip()
            hundename = (entry.get("Hundename") or "").strip() or f"Hund_{lic}"

            dog_ext = f"dog_{lic}"
            dogs.setdefault(dog_ext, {
                "external_id": dog_ext,
                "name":        hundename,
                "license_no":  lic,
                "license_kind": "CH",
            })

            person_ext = f"p_{(nachname + vorname).lower().replace(' ', '_') or lic}"
            persons.setdefault(person_ext, {
                "external_id": person_ext,
                "first_name":  vorname,
                "last_name":   nachname,
                "email":       (entry.get("Email") or None),
            })

            # Pro (Hund, Klasse, Kategorie) einmal eine Registration
            reg_key = (lic, klasse, kategorie)
            if reg_key in seen_reg:
                continue
            seen_reg.add(reg_key)
            reg_ext = f"reg_{lic}_{klasse}_{kategorie}".lower().replace(" ", "_")
            registrations.append({
                "external_id":                reg_ext,
                "event_external_id":          event_external_id,
                "dog_external_id":            dog_ext,
                "handler_person_external_id": person_ext,
                "category_code":              kategorie,
                "class_level":                klasse,
                "status":                     "CONFIRMED",
                "tka_event_check_status":     "PENDING",
                "start_number":               start_no_by_lic.get(lic),
                "can_start":                  True,
                "eligibility":                {"payment_status": "NOT_MANAGED"},
            })

    start_numbers_payload = {
        "event_external_id": event_external_id,
        "locked":            bool(event.get("startnummern_locked", False)),
        "generated_at":      _utc_now_iso(),
        "rule_set":          None,
        "numbers": [
            {
                "registration_external_id": f"reg_{lic}_{None}_{None}",   # Fallback; nutzt 1. Registration
                "license_no":               lic,
                "start_no":                 snr,
            }
            for lic, snr in start_no_by_lic.items()
        ],
    }
    # Korrekte registration_external_id mappen (erste Registration pro Lizenz)
    lic_to_reg = {}
    for reg in registrations:
        dog_ext = reg.get("dog_external_id") or ""
        if dog_ext.startswith("dog_"):
            lic = dog_ext[4:]
            lic_to_reg.setdefault(lic, reg["external_id"])
    for n in start_numbers_payload["numbers"]:
        lic = n.get("license_no")
        if lic and lic in lic_to_reg:
            n["registration_external_id"] = lic_to_reg[lic]

    # Schedule
    event_date = (event.get("Datum") or "").strip()   # "YYYY-MM-DD"
    blocks_payload: list[dict] = []
    schedule = event.get("schedule") or {}
    for ring_key, ring_data in (schedule.get("rings") or {}).items():
        for block in ring_data.get("blocks") or []:
            raw_time = (block.get("start_at") or "").strip()   # meist "HH:MM"
            if event_date and raw_time and "T" not in raw_time:
                # HH:MM + event_date → ISO-Timestamp damit Portal-Importer parsen kann
                start_at_iso = f"{event_date}T{raw_time}:00" if len(raw_time) == 5 else f"{event_date}T{raw_time}"
            else:
                start_at_iso = raw_time
            blocks_payload.append({
                "ring":          str(ring_key),
                "start_at":      start_at_iso,
                "discipline":    (block.get("timing_run_type") or "").capitalize() or "Other",
                "category_code": block.get("size_category") or "",
                "class_level":   (block.get("classes") or [None])[0],
                "notes":         block.get("notes") or block.get("title") or "",
            })
    schedule_payload = {
        "event_external_id": event_external_id,
        "timezone":          "Europe/Zurich",
        "locked":            False,
        "blocks":            blocks_payload,
    }

    event_payload = {
        "external_id":  event_external_id,
        "name":         event.get("Bezeichnung") or "",
        "location":     event.get("Ort") or "",
        "starts_at":    event.get("Datum") or None,
        "ends_at":      event.get("Datum_Ende") or event.get("Datum") or None,
        "billing_mode": "ORGANIZER",
    }
    entities_payload = {
        "persons": list(persons.values()),
        "dogs":    list(dogs.values()),
    }
    registrations_payload = registrations

    # EventRuns (Portal hat separate event_runs-Tabelle)
    # Pro (kategorie, klasse, laufart, is_final) ein Eintrag, dedupliziert
    runs_payload = []
    seen_run = set()
    for run in event.get("runs") or []:
        kategorie = run.get("kategorie") or ""
        klasse_raw = run.get("klasse")
        laufart = (run.get("laufart") or "").lower()
        is_final = bool(run.get("is_final"))
        try:
            class_level = int(klasse_raw) if klasse_raw is not None else None
        except (ValueError, TypeError):
            class_level = None
        cat_short = (kategorie[:1] or "L").upper()    # Small→S, Medium→M, etc.
        key = (laufart, cat_short, class_level, is_final)
        if key in seen_run:
            continue
        seen_run.add(key)
        runs_payload.append({
            "run_type":    laufart or "agility",
            "category":    cat_short,
            "class_level": class_level if class_level is not None else 1,
            "is_final":    is_final,
        })

    manifest = {
        "schema":       "agility.exchange.eventexport.v1",
        "generated_at": _utc_now_iso(),
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json",      json.dumps(manifest, ensure_ascii=False))
        zf.writestr("event.json",         json.dumps(event_payload, ensure_ascii=False))
        zf.writestr("entities.json",      json.dumps(entities_payload, ensure_ascii=False))
        zf.writestr("registrations.json", json.dumps(registrations_payload, ensure_ascii=False))
        zf.writestr("start_numbers.json", json.dumps(start_numbers_payload, ensure_ascii=False))
        zf.writestr("schedule.json",      json.dumps(schedule_payload, ensure_ascii=False))
        zf.writestr("runs.json",          json.dumps(runs_payload, ensure_ascii=False))
    return buf.getvalue()


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
                "total_faults":_safe_float(entry.get("fehler_total")),
                "eliminated":  eliminated,
                "status":      status,
                "dog_name":    entry.get("Hundename") or "",
                "handler_name":entry.get("Hundefuehrer") or "",
            })

        if not rows:
            continue  # Lauf ohne Ergebnisse überspringen

        classes.append({
            "ring":          _normalize_ring(run.get("assigned_ring") or run.get("ring")),
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

    # Schema v1.6: optionaler Finalisten-Block für SKBS-SM (siehe project_offline_architektur)
    finalists_payload = _build_finalists_payload(event)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        zf.writestr("results.json",  json.dumps(results_payload, ensure_ascii=False))
        if finalists_payload:
            zf.writestr("finalists.json", json.dumps(finalists_payload, ensure_ascii=False))
    return buf.getvalue()


def _build_finalists_payload(event: dict) -> dict | None:
    """
    Berechnet Finalisten-Liste für SKBS-SM-Events und liefert sie als ZIP-Payload.

    Returns None wenn:
      - Event ist nicht vom Typ SKBS-SM (kein Finalisten-Konzept)
      - Berechnung schlägt fehl
      - Keine Finalisten gefunden

    Format (Schema v1.6):
      {
        "event_external_id": "...",
        "veranstaltungsart": "SKBS-SM",
        "finalists": [
          {"license", "dog_name", "handler_name", "source", "from_class", "quali_rank"},
          ...
        ],
        "open_spots": int,
      }
    """
    art = event.get("Veranstaltungsart")
    if art == "SKBS-SM":
        try:
            from skbs_sm_qualification import calculate_skbs_sm_qualification
            result = calculate_skbs_sm_qualification(event)
        except Exception:
            return None
        finalists = result.get("finalists") or []
        if not finalists:
            return None
        return {
            "event_external_id": event.get("external_id") or event.get("id") or "",
            "veranstaltungsart": "SKBS-SM",
            "finalists":         finalists,
            "open_spots":        result.get("open_spots", 0),
        }

    if art == "BCCS-SM":
        # BCCS: Finalisten je Division (I/L × SM/Nachwuchs), flach mit category+division.
        try:
            from bccs_sm_qualification import calculate_bccs_sm_qualification
            result = calculate_bccs_sm_qualification(event)
        except Exception:
            return None
        finalists = result.get("finalists") or []
        if not finalists:
            return None
        open_total = sum(d.get("open_spots", 0) for d in result.get("divisions", {}).values())
        return {
            "event_external_id": event.get("external_id") or event.get("id") or "",
            "veranstaltungsart": "BCCS-SM",
            "finalists":         finalists,
            "open_spots":        open_total,
        }

    return None


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
            result = json.loads(resp.read().decode("utf-8"))
            _record_status("result_export", ok=True)
            return result
    except Exception as exc:
        _record_status("result_export", ok=False, error=str(exc))
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
