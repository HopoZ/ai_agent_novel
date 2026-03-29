"""
章节写作/规划时，解析「当前聚焦」的时间线事件 id（ev:timeline:*）。
"""

from __future__ import annotations

from typing import Optional

from agents._internal_marks import z7_module_mark
from agents.persistence.graph_tables import resolve_chapter_event_ids, resolve_chapter_timeline_event_id
from agents.state.state_models import NovelState
from agents.persistence.storage import load_chapter

_MODULE_REV = z7_module_mark("tf")


def resolve_timeline_focus_event_id(
    novel_id: str,
    state: NovelState,
    chapter_index: int,
    time_slot_for_resolve: Optional[str],
    explicit: Optional[str],
) -> Optional[str]:
    x = (explicit or "").strip()
    if x.startswith("ev:timeline:"):
        return x
    chap = load_chapter(novel_id, chapter_index)
    if chap:
        teid = resolve_chapter_timeline_event_id(state, chap)
        if teid:
            return teid
    slot = (time_slot_for_resolve or state.continuity.time_slot or "").strip()
    if chap and str(chap.time_slot or "").strip():
        slot = str(chap.time_slot).strip()
    ids = resolve_chapter_event_ids(state, slot)
    return ids[0] if ids else None
