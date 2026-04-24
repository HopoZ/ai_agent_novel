from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.state.state_models import ChapterRecord, NovelState


def _find_timeline_event(state: NovelState, event_id: str) -> Optional[Dict[str, str]]:
    eid = (event_id or "").strip()
    if not eid:
        return None
    for ev in state.world.timeline or []:
        if (ev.event_id or "").strip() == eid:
            return {
                "event_id": eid,
                "time_slot": str(ev.time_slot or "").strip(),
                "summary": str(ev.summary or "").strip(),
            }
    return None


def build_consistency_audit(
    *,
    state: NovelState,
    chapter: ChapterRecord,
    mode: str,
) -> Dict[str, Any]:
    """
    第一版一致性审计（规则驱动，无模型调用）：
    - 事件归属是否明确
    - 章节 time_slot 与归属事件是否偏离
    - POV 是否出现在 who_is_present
    - beats 数量是否过少
    - 正文字数是否过短（写作模式）
    """
    issues: List[Dict[str, str]] = []
    checks: Dict[str, Any] = {}

    chapter_event_id = (chapter.timeline_event_id or "").strip()
    chapter_slot = str(chapter.time_slot or "").strip()
    event_row = _find_timeline_event(state, chapter_event_id) if chapter_event_id else None

    checks["chapter_event_bound"] = bool(chapter_event_id)
    if not chapter_event_id:
        issues.append(
            {
                "code": "event_unbound",
                "level": "warn",
                "message": "本章未显式归属时间线事件。",
                "suggestion": "建议在时序区选择已有事件，或为本章创建事件后归属。",
            }
        )

    checks["event_exists_in_timeline"] = bool(event_row) if chapter_event_id else None
    if chapter_event_id and (not event_row):
        issues.append(
            {
                "code": "event_not_found",
                "level": "high",
                "message": f"章节绑定事件 {chapter_event_id} 不在当前 world.timeline 中。",
                "suggestion": "请修复章节归属或同步时间线事件列表，避免章节挂载悬空。",
            }
        )

    checks["time_slot_match"] = None
    if event_row:
        event_slot = event_row.get("time_slot", "")
        matched = bool(chapter_slot and event_slot and chapter_slot == event_slot)
        checks["time_slot_match"] = matched
        if (not matched) and chapter_slot and event_slot:
            issues.append(
                {
                    "code": "time_slot_mismatch",
                    "level": "warn",
                    "message": f"章节 time_slot（{chapter_slot}）与归属事件 time_slot（{event_slot}）不一致。",
                    "suggestion": "建议统一章节时间段与事件时间段，或改绑到更匹配的事件。",
                }
            )

    pov = str(chapter.pov_character_id or "").strip()
    present_ids = {str(x.character_id or "").strip() for x in (chapter.who_is_present or []) if str(x.character_id or "").strip()}
    checks["pov_in_presence"] = None if (not pov) else (pov in present_ids)
    if pov and pov not in present_ids:
        issues.append(
            {
                "code": "pov_not_present",
                "level": "warn",
                "message": f"POV 角色 {pov} 未出现在本章 who_is_present 列表。",
                "suggestion": "建议补齐出场角色，保证视角人物与出场集合一致。",
            }
        )

    beats_n = len(chapter.beats or [])
    checks["beats_count"] = beats_n
    if beats_n < 2:
        issues.append(
            {
                "code": "beats_too_few",
                "level": "warn",
                "message": f"本章 beats 仅 {beats_n} 条，结构可能过薄。",
                "suggestion": "建议补充冲突、转折或收束节拍，提升章节结构完整度。",
            }
        )

    content_len = len(str(chapter.content or "").strip())
    checks["content_length"] = content_len
    if mode in {"write_chapter", "revise_chapter", "expand_chapter"} and content_len < 200:
        issues.append(
            {
                "code": "content_too_short",
                "level": "warn",
                "message": f"正文长度约 {content_len} 字，可能不足以承载当前章节目标。",
                "suggestion": "建议扩写关键场景（冲突、行动、结果）并补齐过渡。",
            }
        )

    score = 100
    for it in issues:
        level = str(it.get("level") or "").lower()
        if level == "high":
            score -= 25
        elif level == "warn":
            score -= 10
    score = max(0, score)

    severity = "ok"
    if any(str(x.get("level") or "").lower() == "high" for x in issues):
        severity = "high"
    elif issues:
        severity = "warn"

    block_reasons: List[Dict[str, str]] = []
    for it in issues:
        lvl = str(it.get("level") or "").lower()
        code = str(it.get("code") or "")
        if lvl == "high":
            block_reasons.append(
                {
                    "code": code or "high_risk",
                    "message": str(it.get("message") or "").strip() or "存在高危一致性冲突。",
                }
            )

    recommended_actions: List[str] = []
    code_set = {str(x.get("code") or "") for x in issues}
    if "event_unbound" in code_set:
        recommended_actions.append("在时序区为本章显式绑定已有事件，避免章节游离。")
    if "event_not_found" in code_set:
        recommended_actions.append("检查章节绑定事件是否仍在 timeline 中，必要时重绑事件。")
    if "time_slot_mismatch" in code_set:
        recommended_actions.append("统一 chapter.time_slot 与归属事件 time_slot。")
    if "pov_not_present" in code_set:
        recommended_actions.append("将 POV 角色加入 who_is_present，保持叙事视角一致。")
    if "beats_too_few" in code_set or "content_too_short" in code_set:
        recommended_actions.append("补齐章节结构卡：目标、冲突、转折、结果。")

    return {
        "score": score,
        "severity": severity,
        "issue_count": len(issues),
        "issues": issues,
        "checks": checks,
        "block_reasons": block_reasons,
        "recommended_actions": recommended_actions,
    }

