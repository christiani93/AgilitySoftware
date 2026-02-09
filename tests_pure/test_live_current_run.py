from web_app.live.live_state import persist_current_run, resolve_judge_from_run_block


def test_resolve_judge_from_run_block():
    judges = [
        {"id": "j1", "firstname": "Max", "lastname": "Mustermann"},
    ]
    block = {"judge_id": "j1"}
    assert resolve_judge_from_run_block(block, judges) == "Max Mustermann"
    assert resolve_judge_from_run_block({"judge_name": "Judge X"}, judges) == "Judge X"
    assert resolve_judge_from_run_block({}, judges) == "—"


def test_persist_current_run():
    events = [{"id": "e1", "current_run_blocks": {}}]
    assert persist_current_run(events, "e1", "1", "blk_1")
    assert events[0]["current_run_blocks"]["1"]["run_block_id"] == "blk_1"
