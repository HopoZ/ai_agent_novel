"""next_state 合并。包结构与职责见 `agents/README.md`。"""

from __future__ import annotations

import json
from typing import Dict

from agents._internal_marks import z7_module_mark
from agents.persistence.storage import list_chapters

from .state_models import CharacterState, ContinuityState, NovelState, WorldState

_MODULE_REV = z7_module_mark("sm")


def neighbor_chapters_context(
    novel_id: str,
    target_chapter_index: int,
    enabled: bool = True,
) -> str:
    """
    仅注入“上下相关两章”（上一章 + 下一章）的轻量摘要，控制输入量。
    """
    if not enabled:
        return "[]"
    chapters = list_chapters(novel_id)
    if not chapters:
        return "[]"
    prev_c = None
    next_c = None
    for c in chapters:
        if c.chapter_index < target_chapter_index:
            if (prev_c is None) or (c.chapter_index > prev_c.chapter_index):
                prev_c = c
        elif c.chapter_index > target_chapter_index:
            if (next_c is None) or (c.chapter_index < next_c.chapter_index):
                next_c = c
    selected = [x for x in [prev_c, next_c] if x is not None]
    payload = []
    for c in selected:
        payload.append(
            {
                "chapter_index": c.chapter_index,
                "chapter_preset_name": c.chapter_preset_name,
                "time_slot": c.time_slot,
                "pov_character_id": c.pov_character_id,
                "who_is_present": [p.character_id for p in (c.who_is_present or [])],
                "beats": [
                    {"beat_title": b.beat_title, "summary": b.summary}
                    for b in (c.beats or [])[:6]
                ],
            }
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def merge_state(base: NovelState, patch: NovelState) -> NovelState:
    """
    将模型给出的 next_state（允许是“补丁”）合并到当前 base 状态，避免因输出过长而截断。
    """
    merged = base.model_copy(deep=True)

    # meta（patch 常只给增量；要避免默认值把 base 覆盖坏）
    if patch.meta:
        pm = patch.meta
        mm = merged.meta
        if pm.novel_id:
            mm.novel_id = pm.novel_id
        if pm.novel_title:
            mm.novel_title = pm.novel_title
        if pm.lore_tags:
            mm.lore_tags = pm.lore_tags
        # initialized 一旦为 True，不应被 patch 默认 False 回写
        mm.initialized = bool(mm.initialized or pm.initialized)
        # 章节号只允许前进，不允许因 patch 默认 0 回退
        if isinstance(pm.current_chapter_index, int) and pm.current_chapter_index > mm.current_chapter_index:
            mm.current_chapter_index = pm.current_chapter_index
        merged.meta = mm

    # continuity
    if patch.continuity:
        mc = merged.continuity.model_copy(deep=True)
        pc = patch.continuity
        merged.continuity = ContinuityState(
            time_slot=pc.time_slot or mc.time_slot,
            who_is_present=pc.who_is_present or mc.who_is_present,
            pov_character_id=pc.pov_character_id or mc.pov_character_id,
            current_location=pc.current_location or mc.current_location,
        )

    # characters
    if patch.characters:
        by_id: Dict[str, CharacterState] = {c.character_id: c for c in (base.characters or []) if c.character_id}
        for c in patch.characters:
            if not c.character_id:
                continue
            by_id[c.character_id] = c
        merged.characters = list(by_id.values())

    # world
    if patch.world:
        pb = patch.world
        mb = merged.world.model_copy(deep=True)
        merged.world = WorldState(
            key_rules=pb.key_rules or mb.key_rules,
            factions=pb.factions or mb.factions,
            timeline=mb.timeline,
            open_questions=pb.open_questions or mb.open_questions,
        )
        # timeline append with simple de-dup
        seen = {(t.time_slot, t.summary) for t in (mb.timeline or [])}
        for t in pb.timeline or []:
            k = (t.time_slot, t.summary)
            if k in seen:
                continue
            seen.add(k)
            merged.world.timeline.append(t)

    # recent_summaries
    if patch.recent_summaries:
        merged.recent_summaries = patch.recent_summaries

    return merged
