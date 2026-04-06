from __future__ import annotations

from typing import Iterable


def _entry_id(entry: dict | None) -> str | None:
    if not entry:
        return None
    return entry.get("Lizenznummer") or entry.get("license_number") or entry.get("entry_id")


def _entry_name(entry: dict | None) -> str:
    if not entry:
        return "—"
    first = entry.get("Vorname") or entry.get("vorname") or entry.get("firstname") or ""
    dog = entry.get("Hundename") or entry.get("hundename") or entry.get("dog_name") or ""
    if not first:
        handler = entry.get("Hundefuehrer") or entry.get("Hundeführer") or entry.get("handler_name") or ""
        if handler and "," in handler:
            handler = handler.split(",", 1)[1]
        first = (handler.strip().split() or [""])[0]
    if first and dog:
        return f"{first} {dog}"
    return first or dog or "—"


def _next_id(ids: list[str], current_id: str | None) -> str | None:
    if not ids:
        return None
    if not current_id:
        return ids[0]
    try:
        index = ids.index(current_id)
    except ValueError:
        return ids[0]
    if index + 1 < len(ids):
        return ids[index + 1]
    return None


def _normalize_ids(startlist: Iterable[dict]) -> list[str]:
    ids = []
    for entry in startlist or []:
        entry_id = _entry_id(entry)
        if entry_id:
            ids.append(str(entry_id))
    return ids


def init_ring_entry_state(startlist: Iterable[dict]) -> dict:
    ids = _normalize_ids(startlist)
    current = ids[0] if ids else None
    ready = ids[1] if len(ids) > 1 else None
    return {"current_entry_id": current, "ready_entry_id": ready}


def apply_start_impulse(state: dict, startlist: Iterable[dict]) -> dict:
    ids = _normalize_ids(startlist)
    current = (state or {}).get("current_entry_id")
    ready = (state or {}).get("ready_entry_id")
    if not ids:
        return {"current_entry_id": current, "ready_entry_id": ready}
    if ready in ids:
        next_ready = _next_id(ids, ready)
    elif current in ids:
        next_ready = _next_id(ids, current)
    else:
        next_ready = ids[0]
    return {"current_entry_id": current, "ready_entry_id": next_ready}


def apply_result_saved(state: dict, startlist: Iterable[dict], saved_entry_id: str | None) -> dict:
    ids = _normalize_ids(startlist)
    current = (state or {}).get("current_entry_id")
    ready = (state or {}).get("ready_entry_id")
    if not ids or not saved_entry_id or saved_entry_id != current:
        return {"current_entry_id": current, "ready_entry_id": ready}
    next_current = ready if ready in ids else _next_id(ids, current)
    next_ready = _next_id(ids, next_current)
    return {"current_entry_id": next_current, "ready_entry_id": next_ready}


def build_view_model_from_state(
    state: dict,
    startlist: Iterable[dict],
    run_meta: dict | None = None,
    ranking_top: Iterable[dict] | None = None,
    last_results: Iterable[dict] | None = None,
) -> dict:
    ids = _normalize_ids(startlist)
    current_id = (state or {}).get("current_entry_id")
    ready_id = (state or {}).get("ready_entry_id")
    startlist_next = []
    for entry in startlist or []:
        entry_id = _entry_id(entry)
        if not entry_id:
            continue
        startlist_next.append({
            "entry_id": str(entry_id),
            "name": _entry_name(entry),
            "current": str(entry_id) == str(current_id),
            "ready": str(entry_id) == str(ready_id),
        })
    def _find_entry(entry_id: str | None) -> dict:
        for entry in startlist or []:
            if str(_entry_id(entry)) == str(entry_id):
                return {"entry_id": str(entry_id), "name": _entry_name(entry)}
        return {"entry_id": entry_id, "name": "—"}

    return {
        "run_meta": run_meta or {},
        "current": _find_entry(current_id) if current_id else {"entry_id": None, "name": "—"},
        "ready": _find_entry(ready_id) if ready_id else {"entry_id": None, "name": "—"},
        "startlist_next": startlist_next,
        "ranking_top": list(ranking_top or []),
        "last_results": list(last_results or []),
        "startlist_ids": ids,
    }
