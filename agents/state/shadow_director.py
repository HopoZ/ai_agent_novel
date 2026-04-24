from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from agents.state.state_models import NovelState


def _terms(text: str) -> Set[str]:
    raw = [p.strip().lower() for p in re.split(r"[\s,，。！？、;；:：()（）\[\]{}<>\"'`]+", str(text or "")) if p.strip()]
    return {x for x in raw if len(x) >= 2}


def _infer_conflict_type(user_task: str, structure_card: Optional[Dict[str, Any]]) -> str:
    t = str(user_task or "").lower()
    g = str((structure_card or {}).get("goal") or "")
    mix = f"{t}\n{g}".lower()
    if any(k in mix for k in ("追", "逃", "潜入", "突围", "战", "杀", "袭击")):
        return "动作对抗"
    if any(k in mix for k in ("秘密", "误会", "真相", "身份", "证据")):
        return "信息差冲突"
    if any(k in mix for k in ("抉择", "信任", "背叛", "立场", "道德")):
        return "价值观冲突"
    if any(k in mix for k in ("谈判", "交易", "权力", "家族", "势力")):
        return "利益博弈冲突"
    return "角色目标冲突"


def _infer_foreshadow_target(state: NovelState) -> str:
    if state.world.open_questions:
        q = str(state.world.open_questions[0] or "").strip()
        if q:
            return f"优先回收开放问题：{q}"
    if state.recent_summaries:
        s = str(state.recent_summaries[-1] or "").strip()
        if s:
            short = s if len(s) <= 80 else (s[:80].rstrip() + "...")
            return f"承接上一章尾部张力：{short}"
    if state.world.timeline:
        ev = state.world.timeline[-1]
        slot = str(getattr(ev, "time_slot", "") or "").strip()
        smy = str(getattr(ev, "summary", "") or "").strip()
        if slot or smy:
            return f"围绕最新时间线事件延展：{slot}｜{smy}"
    return "回收前文埋设的承诺、线索或角色心结。"


def _recommend_supporting_characters(
    *,
    state: NovelState,
    user_task: str,
    pov_ids: List[str],
    existing_supporting: List[str],
    limit: int = 2,
) -> List[Dict[str, str]]:
    chosen = {str(x).strip() for x in (pov_ids + existing_supporting) if str(x).strip()}
    q = _terms(user_task)
    cand: List[Dict[str, Any]] = []
    for c in state.characters or []:
        cid = str(getattr(c, "character_id", "") or "").strip()
        if not cid or cid in chosen:
            continue
        label = str(getattr(c, "name", None) or "").strip() or cid
        score = 0
        text_bag = " ".join(
            [
                str(getattr(c, "description", "") or ""),
                " ".join([str(x or "") for x in (getattr(c, "goals", []) or [])]),
                " ".join([str(x or "") for x in (getattr(c, "known_facts", []) or [])]),
            ]
        ).lower()
        if q and any(t in text_bag for t in q):
            score += 2
        if getattr(c, "goals", None):
            score += 1
        if getattr(c, "known_facts", None):
            score += 1
        cand.append({"id": cid, "label": label, "score": score})
    cand.sort(key=lambda x: (int(x.get("score") or 0), str(x.get("id") or "")), reverse=True)
    out: List[Dict[str, str]] = []
    for item in cand[: max(0, int(limit))]:
        out.append({"id": str(item["id"]), "label": str(item["label"])})
    return out


def build_shadow_director_package(
    *,
    state: NovelState,
    user_task: str,
    inferred_time_slot: Optional[str],
    timeline_focus_id: Optional[str],
    pov_ids: List[str],
    existing_supporting: List[str],
    structure_card: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    conflict_type = _infer_conflict_type(user_task, structure_card)
    foreshadow_target = _infer_foreshadow_target(state)
    supporting = _recommend_supporting_characters(
        state=state,
        user_task=user_task,
        pov_ids=pov_ids,
        existing_supporting=existing_supporting,
        limit=2,
    )
    event_focus = str(timeline_focus_id or "").strip()
    if not event_focus:
        event_focus = str((structure_card or {}).get("event_binding") or "").strip()
    digest_lines = [
        f"冲突类型：{conflict_type}",
        f"伏笔回收：{foreshadow_target}",
    ]
    if supporting:
        digest_lines.append("推荐配角：" + "、".join([x["label"] for x in supporting]))
    if inferred_time_slot:
        digest_lines.append(f"时间段：{inferred_time_slot}")
    return {
        "strategy_profile": "director_autopilot_v2",
        "auto_apply": True,
        "digest": "\n".join(digest_lines),
        "suggestions": {
            "conflict_type": conflict_type,
            "foreshadow_target": foreshadow_target,
            "supporting_characters": supporting,
            "timeline_focus_id": event_focus,
        },
        "applied_fields": ["conflict_type", "foreshadow_target", "supporting_characters"],
    }

