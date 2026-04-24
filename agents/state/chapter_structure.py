from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.state.state_models import NovelState


def _clean_text(x: Any) -> str:
    return str(x or "").strip()


def _pick_event_binding(
    *,
    state: NovelState,
    timeline_event_focus_id: Optional[str],
    inferred_time_slot: Optional[str],
    req_existing_event_id: Optional[str],
    req_new_event_time_slot: Optional[str],
    req_new_event_summary: Optional[str],
) -> str:
    eid = _clean_text(req_existing_event_id) or _clean_text(timeline_event_focus_id)
    if eid.startswith("ev:timeline:"):
        for ev in state.world.timeline or []:
            if _clean_text(getattr(ev, "event_id", "")) == eid:
                slot = _clean_text(getattr(ev, "time_slot", ""))
                smy = _clean_text(getattr(ev, "summary", ""))
                if slot or smy:
                    return f"{eid}（{slot}｜{smy}）"
                return eid
        return eid
    new_slot = _clean_text(req_new_event_time_slot)
    new_summary = _clean_text(req_new_event_summary)
    if new_slot or new_summary:
        return f"新建事件（{new_slot or '未标注时间'}｜{new_summary or '未填摘要'}）"
    return _clean_text(inferred_time_slot)


def _infer_goal(user_task: str, chapter_index: int) -> str:
    t = _clean_text(user_task)
    if not t:
        return f"推进第 {chapter_index} 章剧情目标"
    first = t.splitlines()[0].strip()
    if len(first) > 70:
        first = first[:70].rstrip() + "..."
    return first or f"推进第 {chapter_index} 章剧情目标"


def _infer_conflict(user_task: str, state: NovelState) -> str:
    t = _clean_text(user_task)
    if "冲突" in t or "对抗" in t or "矛盾" in t:
        return "沿用任务中指定冲突，确保冲突有行动与结果。"
    pov = _clean_text(state.continuity.pov_character_id)
    if pov:
        return f"{pov} 在目标推进中遭遇阻力并作出选择。"
    return "主角在推进目标时遭遇阻力并作出选择。"


def build_locked_structure_card(
    *,
    state: NovelState,
    user_task: str,
    chapter_index: int,
    inferred_time_slot: Optional[str],
    timeline_event_focus_id: Optional[str],
    req_existing_event_id: Optional[str],
    req_new_event_time_slot: Optional[str],
    req_new_event_summary: Optional[str],
    existing_card: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    src = dict(existing_card or {})
    goal = _clean_text(src.get("goal")) or _infer_goal(user_task, chapter_index)
    conflict = _clean_text(src.get("conflict")) or _infer_conflict(user_task, state)
    turning_point = _clean_text(src.get("turning_point")) or "在中后段触发一次信息反转或代价升级。"
    foreshadow_payoff = _clean_text(src.get("foreshadow_payoff")) or "至少回收或推进一个既有伏笔。"
    event_binding = _clean_text(src.get("event_binding")) or _pick_event_binding(
        state=state,
        timeline_event_focus_id=timeline_event_focus_id,
        inferred_time_slot=inferred_time_slot,
        req_existing_event_id=req_existing_event_id,
        req_new_event_time_slot=req_new_event_time_slot,
        req_new_event_summary=req_new_event_summary,
    )
    return {
        "version": "v2",
        "chapter_index": int(chapter_index),
        "time_slot_hint": _clean_text(inferred_time_slot) or _clean_text(state.continuity.time_slot),
        "goal": goal,
        "conflict": conflict,
        "turning_point": turning_point,
        "foreshadow_payoff": foreshadow_payoff,
        "event_binding": event_binding,
        "locked": True,
        "source": "auto_locked",
    }


def evaluate_structure_gate(card: Dict[str, Any]) -> Dict[str, Any]:
    field_map = {
        "goal": "目标",
        "conflict": "冲突",
        "event_binding": "事件归属",
    }
    missing_fields = [label for key, label in field_map.items() if not _clean_text(card.get(key))]
    needs_ack = len(missing_fields) > 0
    risk_message = ""
    if needs_ack:
        risk_message = f"结构卡最小项未满足：{' / '.join(missing_fields)}。"
    return {
        "version": "v2",
        "missing_fields": missing_fields,
        "needs_ack": needs_ack,
        "risk_message": risk_message,
        "card": card,
    }

