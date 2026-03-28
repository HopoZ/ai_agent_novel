import json
import os
from pathlib import Path


def _write_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def test_infer_time_slot_interval_and_legacy(tmp_path, monkeypatch):
    # Keep import path stable (project root), but isolate storage via cwd switch after import
    import sys
    from pathlib import Path as _Path

    repo_root = _Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from webapp.backend.server import RunModeRequest, _infer_time_slot

    # Run in isolated temp cwd so server.py uses temp ./storage
    monkeypatch.chdir(tmp_path)

    novel_id = "11111111-1111-1111-1111-111111111111"
    base = tmp_path / "storage" / "novels" / novel_id

    # Minimal state.json with timeline
    _write_json(
        base / "state.json",
        {
            "meta": {"novel_id": novel_id, "initialized": True, "current_chapter_index": 0, "lore_tags": []},
            "continuity": {"time_slot": "t0", "who_is_present": [], "pov_character_id": None, "current_location": None},
            "characters": [],
            "world": {
                "timeline": [
                    {"time_slot": "A", "chapter_index": None, "summary": "a"},
                    {"time_slot": "B", "chapter_index": None, "summary": "b"},
                ]
            },
            "recent_summaries": [],
        },
    )

    # Minimal chapter record to resolve ev:chapter:3
    _write_json(
        base / "chapters" / "3.json",
        {
            "chapter_index": 3,
            "time_slot": "C",
            "pov_character_id": None,
            "who_is_present": [],
            "beats": [],
            "content": "",
            "usage_metadata": {},
        },
    )

    # manual wins
    req = RunModeRequest(mode="plan_only", user_task="x", time_slot_override="MANUAL")
    assert _infer_time_slot(novel_id, req) == "MANUAL"

    # interval: after+before
    req = RunModeRequest(mode="plan_only", user_task="x", insert_after_id="ev:timeline:0", insert_before_id="ev:chapter:3")
    assert _infer_time_slot(novel_id, req) == "A之后~C之前"

    # interval: after only
    req = RunModeRequest(mode="plan_only", user_task="x", insert_after_id="ev:timeline:1")
    assert _infer_time_slot(novel_id, req) == "B之后"

    # interval: before only
    req = RunModeRequest(mode="plan_only", user_task="x", insert_before_id="ev:chapter:3")
    assert _infer_time_slot(novel_id, req) == "C之前"

    # legacy: insert_anchor_id fallback
    req = RunModeRequest(mode="plan_only", user_task="x", insert_anchor_id="ev:timeline:0")
    assert _infer_time_slot(novel_id, req) == "A"

