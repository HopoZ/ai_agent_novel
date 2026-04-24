from agents.state.consistency_audit import build_consistency_audit
from agents.state.state_models import ChapterRecord, NovelState


def _make_state() -> NovelState:
    return NovelState.model_validate(
        {
            "meta": {
                "novel_id": "n-audit",
                "novel_title": "audit",
                "initialized": True,
                "current_chapter_index": 3,
            },
            "continuity": {"time_slot": "第2日 上午", "pov_character_id": "lin", "who_is_present": ["lin"]},
            "characters": [
                {"id": "lin", "name": "林川"},
                {"id": "su", "name": "苏瑶"},
            ],
            "world": {
                "timeline": [
                    {"event_id": "ev1", "time_slot": "第1日 夜", "summary": "夜巡事件"},
                    {"event_id": "ev2", "time_slot": "第2日 上午", "summary": "因误会引发冲突后谈判"},
                ]
            },
            "recent_summaries": [],
        }
    )


def _make_chapter(
    *,
    idx: int,
    time_slot: str,
    content: str,
    event_id: str | None = None,
    beat_slots: list[str] | None = None,
    beat_summaries: list[str] | None = None,
    who: list[dict] | None = None,
) -> ChapterRecord:
    slots = beat_slots or []
    summaries = beat_summaries or []
    beats = []
    for i, s in enumerate(summaries):
        beats.append(
            {
                "beat_title": f"b{i+1}",
                "summary": s,
                "time_slot": (slots[i] if i < len(slots) else None),
            }
        )
    return ChapterRecord.model_validate(
        {
            "chapter_index": idx,
            "timeline_event_id": event_id,
            "time_slot": time_slot,
            "pov_character_id": "lin",
            "who_is_present": who
            or [
                {"character_id": "lin", "status_at_scene": "在北城"},
                {"character_id": "su", "status_at_scene": "在北城"},
            ],
            "beats": beats,
            "content": content,
            "usage_metadata": {},
        }
    )


def test_timeline_reverse_high_and_block_reason():
    st = _make_state()
    chapter = _make_chapter(
        idx=2,
        time_slot="第2日 上午",
        event_id="ev2",
        content="众人推进调查并发生冲突，随后在城门继续对峙。",
        beat_slots=["第2日 上午", "第1日 夜"],
        beat_summaries=["调查推进", "返回旧案现场"],
    )
    out = build_consistency_audit(state=st, chapter=chapter, mode="write_chapter")
    codes = {x["code"] for x in out["issues"]}
    block_codes = {x["code"] for x in out["block_reasons"]}
    assert "timeline_reverse" in codes
    assert "timeline_reverse" in block_codes
    assert any("时间顺序" in x for x in out["recommended_actions"])


def test_character_teleport_high_without_transition():
    st = _make_state()
    prev_chapter = _make_chapter(
        idx=1,
        time_slot="第2日 上午",
        event_id="ev2",
        content="林川仍在北城继续搜查线索。",
        beat_slots=["第2日 上午"],
        beat_summaries=["北城巡逻"],
        who=[{"character_id": "lin", "status_at_scene": "在北城"}],
    )
    chapter = _make_chapter(
        idx=2,
        time_slot="第2日 上午",
        event_id="ev2",
        content="林川与队伍在南港会合，战斗爆发。",
        beat_slots=["第2日 上午"],
        beat_summaries=["南港对峙"],
        who=[{"character_id": "lin", "status_at_scene": "在南港"}],
    )
    out = build_consistency_audit(
        state=st,
        chapter=chapter,
        mode="write_chapter",
        previous_chapter=prev_chapter,
    )
    codes = {x["code"] for x in out["issues"]}
    assert "character_teleport" in codes


def test_character_teleport_not_triggered_with_transition_marker():
    st = _make_state()
    prev_chapter = _make_chapter(
        idx=1,
        time_slot="第2日 上午",
        event_id="ev2",
        content="林川仍在北城继续搜查线索。",
        who=[{"character_id": "lin", "status_at_scene": "在北城"}],
    )
    chapter = _make_chapter(
        idx=2,
        time_slot="第2日 上午",
        event_id="ev2",
        content="林川连夜赶到南港后与队伍会合。",
        who=[{"character_id": "lin", "status_at_scene": "在南港"}],
    )
    out = build_consistency_audit(
        state=st,
        chapter=chapter,
        mode="write_chapter",
        previous_chapter=prev_chapter,
    )
    codes = {x["code"] for x in out["issues"]}
    assert "character_teleport" not in codes


def test_relation_mutation_without_event_high():
    st = _make_state()
    chapter = _make_chapter(
        idx=2,
        time_slot="第2日 上午",
        event_id=None,
        content="林川与苏瑶当场反目决裂，气氛骤冷。",
        beat_summaries=["双方关系瞬间恶化"],
    )
    out = build_consistency_audit(state=st, chapter=chapter, mode="write_chapter")
    codes = {x["code"] for x in out["issues"]}
    block_codes = {x["code"] for x in out["block_reasons"]}
    assert "relation_mutation_without_event" in codes
    assert "relation_mutation_without_event" in block_codes
    assert any("关系变化" in x for x in out["recommended_actions"])


def test_relation_mutation_has_event_evidence_not_triggered():
    st = _make_state()
    chapter = _make_chapter(
        idx=2,
        time_slot="第2日 上午",
        event_id="ev2",
        content="误会解除后，两人达成和解并继续调查。",
        beat_summaries=["冲突升级", "谈判后和解"],
    )
    out = build_consistency_audit(state=st, chapter=chapter, mode="write_chapter")
    codes = {x["code"] for x in out["issues"]}
    assert "relation_mutation_without_event" not in codes
