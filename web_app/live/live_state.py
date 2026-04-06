from __future__ import annotations

from datetime import datetime


def resolve_judge_from_run_block(block: dict, judges: list[dict]) -> str:
    judge_id = (block or {}).get("judge_id") or (block or {}).get("richter_id")
    if judge_id:
        judge_id = str(judge_id)
        for judge in judges or []:
            if str(judge.get("id")) == judge_id:
                first = (judge.get("firstname") or judge.get("vorname") or "").strip()
                last = (judge.get("lastname") or judge.get("nachname") or "").strip()
                return f"{first} {last}".strip() or "Unbekannt"
    if (block or {}).get("judge_name"):
        return block.get("judge_name")
    return "—"


def persist_current_run(events: list[dict], event_id: str, ring_key: str, run_block_id: str | None, run_id: str | None = None) -> bool:
    updated = False
    for event in events:
        if event.get("id") != event_id:
            continue
        current = event.get("current_run_blocks") or {}
        current[str(ring_key)] = {
            "run_block_id": run_block_id,
            "updated_at": datetime.utcnow().isoformat(),
        }
        event["current_run_blocks"] = current
        if run_id:
            current_runs = event.get("current_runs_by_ring") or {}
            current_runs[str(ring_key)] = run_id
            event["current_runs_by_ring"] = current_runs
        updated = True
        break
    return updated
