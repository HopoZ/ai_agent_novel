"""
运行链路辅助：时间段推导、user_task 拼接、章节-事件绑定、写前预构建图谱四表骨架。
供 routes 层调用，无 FastAPI 依赖。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.persistence.graph_tables import (
    ensure_graph_tables,
    load_event_relations,
    replace_timeline_next_edges_from_state,
    save_character_entities,
    save_event_relations,
    save_event_rows,
    timeline_next_graph_neighbors,
)
from agents.persistence.storage import load_chapter, load_state, save_state
from agents.state.state_models import NovelState, TimelineEvent
from webapp.backend.schemas import RunModeRequest


def resolve_anchor_time_slot(novel_id: str, anchor_id: Optional[str]) -> Optional[str]:
    """
    把锚点 id 解析为 time_slot。
    支持：
      - ev:timeline:{idx}
      - ev:chapter:{chapter_index}
    """
    if not anchor_id:
        return None
    anchor = (anchor_id or "").strip()
    if not anchor:
        return None
    try:
        if anchor.startswith("ev:timeline:"):
            idx = int(anchor.split("ev:timeline:", 1)[1])
            st = load_state(novel_id)
            if st and st.world.timeline and 0 <= idx < len(st.world.timeline):
                return st.world.timeline[idx].time_slot
            return None
        if anchor.startswith("ev:chapter:"):
            chap_idx = int(anchor.split("ev:chapter:", 1)[1])
            chap = load_chapter(novel_id, chap_idx)
            return chap.time_slot if chap else None
    except Exception:
        return None
    return None


def infer_time_slot(novel_id: str, req: RunModeRequest) -> Optional[str]:
    """
    time_slot 推导优先级：
      1) time_slot_override（手动）
      2) 区间语义 after/before -> 组合提示
      3) deprecated 的 insert_anchor_id -> 单锚点 time_slot
      4) None（交给 agent 自行延续/推断）
    """
    if req.time_slot_override and str(req.time_slot_override).strip():
        return req.time_slot_override

    existing_slot = resolve_anchor_time_slot(novel_id, req.existing_event_id)
    if existing_slot:
        return existing_slot

    if req.new_event_time_slot and str(req.new_event_time_slot).strip():
        return str(req.new_event_time_slot).strip()

    after_slot = resolve_anchor_time_slot(novel_id, req.insert_after_id)
    before_slot = resolve_anchor_time_slot(novel_id, req.insert_before_id)
    if after_slot and before_slot:
        return f"{after_slot}之后~{before_slot}之前"
    if after_slot:
        return f"{after_slot}之后"
    if before_slot:
        return f"{before_slot}之前"

    legacy_slot = resolve_anchor_time_slot(novel_id, req.insert_anchor_id)
    return legacy_slot


def llm_call_options(req: RunModeRequest) -> Optional[Dict[str, Any]]:
    """将前端可选 LLM 参数转为 agent 使用的 bind 字典；全空则走服务端默认。"""
    opts: Dict[str, Any] = {}
    if req.llm_temperature is not None:
        opts["temperature"] = float(req.llm_temperature)
    if req.llm_top_p is not None:
        opts["top_p"] = float(req.llm_top_p)
    if req.llm_max_tokens is not None:
        opts["max_tokens"] = int(req.llm_max_tokens)
    return opts or None


def timeline_idx(node_id: Optional[str]) -> Optional[int]:
    raw = str(node_id or "").strip()
    if not raw.startswith("ev:timeline:"):
        return None
    try:
        return int(raw.split("ev:timeline:", 1)[1].strip())
    except Exception:
        return None


def apply_chapter_event_selection(next_state: NovelState, chapter_index: int, req: RunModeRequest) -> NovelState:
    """
    新时序语义：
    - existing_event_id: 把本章绑定到已有事件
    - new_event_*: 新建事件并插入前后位置后绑定本章
    """
    tl = list(next_state.world.timeline or [])

    for ev in tl:
        if ev.chapter_index == chapter_index:
            ev.chapter_index = None

    existing_idx = timeline_idx(req.existing_event_id)
    if existing_idx is not None and 0 <= existing_idx < len(tl):
        tl[existing_idx].chapter_index = chapter_index
        next_state.world.timeline = tl
        return next_state

    new_slot = str(req.new_event_time_slot or "").strip()
    new_summary = str(req.new_event_summary or "").strip()
    if not (new_slot and new_summary):
        next_state.world.timeline = tl
        return next_state

    prev_idx = timeline_idx(req.new_event_prev_id)
    next_idx = timeline_idx(req.new_event_next_id)
    insert_at = len(tl)
    if prev_idx is not None and 0 <= prev_idx < len(tl):
        insert_at = prev_idx + 1
    elif next_idx is not None and 0 <= next_idx < len(tl):
        insert_at = next_idx
    if next_idx is not None and 0 <= next_idx < len(tl):
        insert_at = min(insert_at, next_idx)
    insert_at = max(0, min(insert_at, len(tl)))

    tl.insert(
        insert_at,
        TimelineEvent(
            time_slot=new_slot,
            chapter_index=chapter_index,
            summary=new_summary,
        ),
    )
    next_state.world.timeline = tl
    return next_state


def build_llm_user_task(
    novel_id: str,
    raw_user_task: str,
    req: RunModeRequest,
    inferred_time_slot: Optional[str],
    pov_ids: List[str],
) -> str:
    """
    把“用户显式填写的关键约束”拼接到 user_task，确保模型稳定拿到：
    - 本章归属事件（已有/新建）
    - 主视角
    - 重点涉及角色
    """
    base = str(raw_user_task or "").strip()
    lines: List[str] = []

    st = load_state(novel_id)
    timeline = list(st.world.timeline or []) if st else []

    def _event_desc(event_id: str) -> str:
        idx = timeline_idx(event_id)
        if idx is None or not (0 <= idx < len(timeline)):
            return event_id
        ev = timeline[idx]
        return f"{event_id}（{ev.time_slot}｜{ev.summary}）"

    existing_id = str(req.existing_event_id or "").strip()
    if existing_id.startswith("ev:timeline:") and st:
        idx = timeline_idx(existing_id)
        if idx is not None and 0 <= idx < len(timeline):
            ev = timeline[idx]
            lines.append(f"章节归属时间线：{existing_id}（{ev.time_slot}｜{ev.summary}）")
            preds, succs = timeline_next_graph_neighbors(novel_id, existing_id)
            if preds or succs:
                for pid in preds:
                    pi = timeline_idx(pid)
                    if pi is not None and 0 <= pi < len(timeline):
                        pev = timeline[pi]
                        lines.append(
                            f"关系图前置事件（timeline_next）：{pid}（{pev.time_slot}｜{pev.summary}）"
                        )
                for sid in succs:
                    si = timeline_idx(sid)
                    if si is not None and 0 <= si < len(timeline):
                        sev = timeline[si]
                        lines.append(
                            f"关系图后置事件（timeline_next）：{sid}（{sev.time_slot}｜{sev.summary}）"
                        )
        else:
            lines.append(f"章节归属时间线：{existing_id}")
    elif (req.new_event_time_slot or "").strip() and (req.new_event_summary or "").strip():
        lines.append(
            "章节归属时间线（新建事件）："
            f"time_slot={str(req.new_event_time_slot).strip()}，"
            f"summary={str(req.new_event_summary).strip()}"
        )
        prev_id = str(req.new_event_prev_id or "").strip()
        next_id = str(req.new_event_next_id or "").strip()
        if prev_id:
            lines.append(f"新事件前置事件（可选）：{_event_desc(prev_id)}")
        if next_id:
            lines.append(f"新事件后置事件（可选）：{_event_desc(next_id)}")
    else:
        lines.append("章节归属时间线：未显式指定（按系统推导/默认流程）")

    if inferred_time_slot:
        lines.append(f"本章时间段（系统推导）：{inferred_time_slot}")

    if pov_ids:
        lines.append(f"主视角候选：{', '.join([x for x in pov_ids if x])}")

    supporting_ids = [str(x).strip() for x in (req.supporting_character_ids or []) if str(x).strip()]
    if supporting_ids:
        lines.append(f"重点涉及角色：{', '.join(supporting_ids)}")

    lore_tags = [str(x).strip() for x in (req.lore_tags or []) if str(x).strip()]
    if lore_tags:
        lines.append(f"设定标签（lore_tags）：{', '.join(lore_tags)}")

    if not lines:
        return base
    suffix = "\n".join(lines)
    return f"{base}\n\n[系统注入约束]\n{suffix}".strip()


def req_timeline_focus_id(req: RunModeRequest) -> Optional[str]:
    x = (req.existing_event_id or "").strip()
    return x if x.startswith("ev:timeline:") else None


def prebuild_chapter_graph_records(
    novel_id: str,
    req: RunModeRequest,
    chapter_index: int,
    inferred_time_slot: Optional[str],
    pov_ids: List[str],
) -> None:
    """
    生成前预构建图谱四表中的“本章骨架”：
    - event_relations：主要人物 -> ev:chapter:{n} 的 appear 边
    - 若已选择章节归属事件，先把 chapter_index 绑定到 timeline
    """
    st = load_state(novel_id)
    if not st:
        return
    ensure_graph_tables(novel_id)

    has_event_selection = bool(
        (req.existing_event_id or "").strip()
        or ((req.new_event_time_slot or "").strip() and (req.new_event_summary or "").strip())
    )
    if has_event_selection:
        st = apply_chapter_event_selection(st, chapter_index, req)
        save_state(novel_id, st)
        replace_timeline_next_edges_from_state(novel_id, st)

    major_chars = [str(x).strip() for x in (pov_ids or []) if str(x).strip()]
    major_chars.extend([str(x).strip() for x in (req.supporting_character_ids or []) if str(x).strip()])
    if not major_chars and st.continuity.pov_character_id:
        major_chars.append(str(st.continuity.pov_character_id).strip())
    major_chars = [x for i, x in enumerate(major_chars) if x and x not in major_chars[:i]]

    char_map: Dict[str, Dict[str, Any]] = {}
    for c in st.characters or []:
        char_map[str(c.character_id)] = {
            "character_id": c.character_id,
            "description": c.description,
            "current_location": c.current_location,
            "alive": c.alive,
            "goals": list(c.goals or []),
            "known_facts": list(c.known_facts or []),
        }
    for cid in major_chars:
        char_map.setdefault(
            cid,
            {
                "character_id": cid,
                "description": None,
                "current_location": None,
                "alive": None,
                "goals": [],
                "known_facts": [],
            },
        )
    save_character_entities(novel_id, list(char_map.values()))

    save_event_rows(
        novel_id,
        [
            {
                "event_id": f"ev:timeline:{i}",
                "time_slot": str(ev.time_slot or "").strip(),
                "summary": str(ev.summary or "").strip(),
                "chapter_index": ev.chapter_index,
            }
            for i, ev in enumerate(st.world.timeline or [])
        ],
    )

    rows = load_event_relations(novel_id)
    target = f"ev:chapter:{chapter_index}"
    rows = [
        r
        for r in rows
        if not (
            str(r.get("kind", "")).strip().lower() == "appear"
            and str(r.get("target", "")).strip() == target
        )
    ]
    for c in major_chars:
        rows.append(
            {
                "source": f"char:{c}",
                "target": target,
                "label": "主要人物",
                "kind": "appear",
            }
        )
    save_event_relations(novel_id, rows)
