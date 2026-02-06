from web_app.blueprints.routes_live import _persist_current_run, _resolve_judge_from_run_block


def test_resolve_judge_from_run_block():
    judges = [
        {"id": "j1", "firstname": "Max", "lastname": "Mustermann"},
    ]
    block = {"judge_id": "j1"}
    assert _resolve_judge_from_run_block(block, judges) == "Max Mustermann"
    assert _resolve_judge_from_run_block({"judge_name": "Judge X"}, judges) == "Judge X"
    assert _resolve_judge_from_run_block({}, judges) == "—"


def test_persist_current_run():
    events = [{"id": "e1", "current_run_blocks": {}}]
    assert _persist_current_run(events, "e1", "1", "blk_1")
    assert events[0]["current_run_blocks"]["1"]["run_block_id"] == "blk_1"
