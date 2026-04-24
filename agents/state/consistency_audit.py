from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from agents.state.state_models import ChapterRecord, NovelState


def _normalize_text(v: str) -> str:
    return re.sub(r"\s+", "", str(v or "")).lower()


def _time_slot_order_value(time_slot: str) -> Optional[int]:
    """
    将常见 time_slot 文本映射到可比较序值；无法识别则返回 None。
    支持：
    - 数字优先（如 第3日/Day2/2026-04-25）
    - 中文时段（凌晨/清晨/上午/中午/下午/傍晚/夜）
    """
    text = _normalize_text(time_slot)
    if not text:
        return None
    nums = re.findall(r"\d+", text)
    if nums:
        # 只取首个数字作为阶段值（保守策略）
        try:
            base = int(nums[0]) * 10
        except Exception:
            base = 0
    else:
        base = 0

    period_rank = 0
    if any(k in text for k in ("凌晨", "黎明")):
        period_rank = 1
    elif any(k in text for k in ("清晨", "早晨", "早上")):
        period_rank = 2
    elif any(k in text for k in ("上午",)):
        period_rank = 3
    elif any(k in text for k in ("中午", "正午")):
        period_rank = 4
    elif any(k in text for k in ("下午",)):
        period_rank = 5
    elif any(k in text for k in ("傍晚", "黄昏")):
        period_rank = 6
    elif any(k in text for k in ("夜", "深夜", "夜晚")):
        period_rank = 7
    if base == 0 and period_rank == 0:
        return None
    return base + period_rank


def _has_flashback_marker(text: str) -> bool:
    t = _normalize_text(text)
    if not t:
        return False
    markers = ("回忆", "想起", "往昔", "当年", "昔日", "记得")
    return any(k in t for k in markers)


def _extract_location_hints(text: str) -> set[str]:
    raw = str(text or "")
    if not raw.strip():
        return set()
    # 提取“在xxx”这类地点短语（保守启发式）
    matches = re.findall(r"[在于到至往赴回抵达来到进入][\u4e00-\u9fa5A-Za-z0-9]{1,10}", raw)
    out: set[str] = set()
    for m in matches:
        s = _normalize_text(m)
        if len(s) >= 2:
            out.add(s)
    return out


def _has_transition_marker(text: str) -> bool:
    t = _normalize_text(text)
    if not t:
        return False
    markers = (
        "赶到",
        "抵达",
        "前往",
        "返回",
        "回到",
        "转场",
        "赶路",
        "一路",
        "启程",
        "动身",
        "传送",
        "穿梭",
    )
    return any(k in t for k in markers)


def _chapter_text(chapter: Optional[ChapterRecord]) -> str:
    if not chapter:
        return ""
    beat_text = " ".join(str(b.summary or "") for b in (chapter.beats or []))
    who_text = " ".join(str(x.status_at_scene or "") for x in (chapter.who_is_present or []))
    return f"{chapter.content or ''} {beat_text} {who_text}"


def _present_ids(chapter: ChapterRecord) -> set[str]:
    return {
        str(x.character_id or "").strip()
        for x in (chapter.who_is_present or [])
        if str(x.character_id or "").strip()
    }


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
    previous_chapter: Optional[ChapterRecord] = None,
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

    # --- 高危规则：时间线反转 ---
    chapter_text = _chapter_text(chapter)
    beat_slots = [str(b.time_slot or "").strip() for b in (chapter.beats or []) if str(b.time_slot or "").strip()]
    slot_values = [_time_slot_order_value(x) for x in beat_slots]
    checks["timeline_reverse"] = False
    for idx in range(1, len(slot_values)):
        cur = slot_values[idx]
        prev = slot_values[idx - 1]
        if cur is None or prev is None:
            continue
        if cur < prev and (not _has_flashback_marker(chapter_text)):
            checks["timeline_reverse"] = True
            issues.append(
                {
                    "code": "timeline_reverse",
                    "level": "high",
                    "message": f"章节 beats 出现时间逆序：{beat_slots[idx - 1]} -> {beat_slots[idx]}。",
                    "suggestion": "请重排 beats 时间顺序，或在正文显式补充回忆/倒叙标记。",
                }
            )
            break

    # --- 高危规则：角色瞬移 ---
    checks["character_teleport"] = False
    if previous_chapter:
        prev_ids = _present_ids(previous_chapter)
        curr_ids = _present_ids(chapter)
        overlap_ids = [cid for cid in curr_ids if cid in prev_ids]
        prev_slot_v = _time_slot_order_value(str(previous_chapter.time_slot or ""))
        curr_slot_v = _time_slot_order_value(chapter_slot)
        prev_locs = _extract_location_hints(_chapter_text(previous_chapter))
        curr_locs = _extract_location_hints(chapter_text)
        same_or_reverse_time = (
            prev_slot_v is not None
            and curr_slot_v is not None
            and curr_slot_v <= prev_slot_v
        )
        if overlap_ids and prev_locs and curr_locs and prev_locs.isdisjoint(curr_locs) and same_or_reverse_time:
            if not _has_transition_marker(chapter_text):
                checks["character_teleport"] = True
                issues.append(
                    {
                        "code": "character_teleport",
                        "level": "high",
                        "message": f"角色 {overlap_ids[0]} 在相邻章节中地点突变且无过渡线索，疑似“瞬移”。",
                        "suggestion": "请补充移动/转场事件，或修正 time_slot 与出场状态描述。",
                    }
                )

    # --- 高危规则：关系突变无事件依据 ---
    checks["relation_mutation_without_event"] = False
    relation_mutation_markers = (
        "反目",
        "决裂",
        "背叛",
        "和解",
        "结盟",
        "化敌为友",
        "从敌对到同盟",
        "从陌生到亲密",
    )
    relation_evidence_markers = (
        "冲突",
        "谈判",
        "误会",
        "揭露",
        "救援",
        "告白",
        "决斗",
        "交易",
        "相认",
        "事件",
    )
    mutation_hit = any(k in chapter_text for k in relation_mutation_markers)
    if mutation_hit:
        event_summary = str((event_row or {}).get("summary") or "")
        beat_text = " ".join(str(b.summary or "") for b in (chapter.beats or []))
        evidence_text = f"{event_summary} {beat_text}"
        has_event_binding = bool(chapter_event_id and event_row)
        has_evidence = any(k in evidence_text for k in relation_evidence_markers)
        if (not has_event_binding) or (not has_evidence):
            checks["relation_mutation_without_event"] = True
            issues.append(
                {
                    "code": "relation_mutation_without_event",
                    "level": "high",
                    "message": "章节出现关系突变信号，但未提供可追溯事件依据。",
                    "suggestion": "请绑定支撑该关系变化的时间线事件，并在 beats 中写明触发过程。",
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
    if "timeline_reverse" in code_set:
        recommended_actions.append("校正章节时间顺序；若为倒叙，请在章节中显式标注回忆触发点。")
    if "character_teleport" in code_set:
        recommended_actions.append("为关键角色补充移动/转场桥段，避免同时间段跨地点瞬移。")
    if "relation_mutation_without_event" in code_set:
        recommended_actions.append("为关系变化绑定可追溯事件，并在 beats 标注变化原因与过程。")

    return {
        "score": score,
        "severity": severity,
        "issue_count": len(issues),
        "issues": issues,
        "checks": checks,
        "block_reasons": block_reasons,
        "recommended_actions": recommended_actions,
    }

