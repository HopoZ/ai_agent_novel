"""
运行链路辅助：时间段推导、user_task 拼接、章节-事件绑定、写前预构建图谱四表骨架。
供 routes 层调用，无 FastAPI 依赖。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from agents.persistence.graph_tables import (
    ensure_graph_tables,
    load_event_relations,
    new_timeline_event_id,
    patch_new_event_timeline_next_edges,
    replace_timeline_next_edges_from_state,
    save_character_entities,
    save_event_relations,
    save_event_rows,
    timeline_index_for_node_id,
    timeline_next_graph_neighbors,
)
from agents.persistence.storage import load_chapter, load_state, save_state
from agents.state.state_models import NovelState, TimelineEvent
from webapp.backend.schemas import RunModeRequest


def uses_new_timeline_event_for_chapter(req: RunModeRequest) -> bool:
    """
    章节归属为「新建事件」（填了 time_slot+summary）且未选已有 ev:timeline 时返回 True。
    用于压缩 state 注入：此类运行无 focus，可不向模型附带 world.timeline。
    """
    existing = (req.existing_event_id or "").strip()
    if existing.startswith("ev:timeline:"):
        return False
    return bool((req.new_event_time_slot or "").strip() and (req.new_event_summary or "").strip())


def resolve_anchor_time_slot(novel_id: str, anchor_id: Optional[str]) -> Optional[str]:
    """
    把锚点 id 解析为 time_slot。
    支持：
      - ev:timeline:{稳定id 或 列表下标数字}（下标仅兼容旧请求）
      - ev:chapter:{chapter_index}
    """
    if not anchor_id:
        return None
    anchor = (anchor_id or "").strip()
    if not anchor:
        return None
    try:
        if anchor.startswith("ev:timeline:"):
            st = load_state(novel_id)
            if not st or not st.world.timeline:
                return None
            ti = timeline_index_for_node_id(st, anchor)
            if ti is not None and 0 <= ti < len(st.world.timeline):
                return st.world.timeline[ti].time_slot
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


def apply_chapter_event_selection(
    next_state: NovelState, chapter_index: int, req: RunModeRequest
) -> Tuple[NovelState, Optional[str]]:
    """
    时间线侧：不再把「章号」写入 timeline。
    - existing_event_id：不再改 state（章节与时间线对齐仅靠 time_slot）
    - new_event_*：仍可在列表中插入新事件（无 chapter_index 字段）
    返回 (state, 若本次插入了新时间线事件则为其 event_id，否则 None)。
    """
    tl = list(next_state.world.timeline or [])

    existing_idx = timeline_index_for_node_id(next_state, req.existing_event_id)
    if existing_idx is not None and 0 <= existing_idx < len(tl):
        next_state.world.timeline = tl
        return next_state, None

    new_slot = str(req.new_event_time_slot or "").strip()
    new_summary = str(req.new_event_summary or "").strip()
    if not (new_slot and new_summary):
        next_state.world.timeline = tl
        return next_state, None

    prev_idx = timeline_index_for_node_id(next_state, req.new_event_prev_id)
    next_idx = timeline_index_for_node_id(next_state, req.new_event_next_id)
    insert_at = len(tl)
    if prev_idx is not None and 0 <= prev_idx < len(tl):
        insert_at = prev_idx + 1
    elif next_idx is not None and 0 <= next_idx < len(tl):
        insert_at = next_idx
    if next_idx is not None and 0 <= next_idx < len(tl):
        insert_at = min(insert_at, next_idx)
    insert_at = max(0, min(insert_at, len(tl)))

    new_eid = new_timeline_event_id()
    tl.insert(
        insert_at,
        TimelineEvent(
            event_id=new_eid,
            time_slot=new_slot,
            summary=new_summary,
        ),
    )
    next_state.world.timeline = tl
    return next_state, new_eid


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
    mode = str(req.mode or "").strip()
    if mode == "expand_chapter":
        base = (
            "[扩写模式] 下方用户任务中的正文是「待扩写种子」（短文/梗概/片段）。"
            "规划须围绕该种子设计 beats；正文阶段须扩写为约 4000～5000 字的连贯章节。\n\n"
        ) + base
    elif mode == "optimize_suggestions":
        base = (
            "[优化建议模式] 请只输出修改与优化建议（分条、可执行），设计爽点or深刻点or转折点，不要输出完整章节正文。\n\n"
        ) + base

    lines: List[str] = []

    st = load_state(novel_id)
    timeline = list(st.world.timeline or []) if st else []

    def _event_desc(event_id: str) -> str:
        idx = timeline_index_for_node_id(st, event_id) if st else None
        if idx is None or not (0 <= idx < len(timeline)):
            return event_id
        ev = timeline[idx]
        return f"{event_id}（{ev.time_slot}｜{ev.summary}）"

    if mode != "optimize_suggestions":
        existing_id = str(req.existing_event_id or "").strip()
        if existing_id.startswith("ev:timeline:") and st:
            idx = timeline_index_for_node_id(st, existing_id)
            if idx is not None and 0 <= idx < len(timeline):
                ev = timeline[idx]
                lines.append(f"章节归属时间线：{existing_id}（{ev.time_slot}｜{ev.summary}）")
                preds, succs = timeline_next_graph_neighbors(novel_id, existing_id)
                if preds or succs:
                    for pid in preds:
                        pi = timeline_index_for_node_id(st, pid)
                        if pi is not None and 0 <= pi < len(timeline):
                            pev = timeline[pi]
                            lines.append(
                                f"关系图前置事件（timeline_next）：{pid}（{pev.time_slot}｜{pev.summary}）"
                            )
                    for sid in succs:
                        si = timeline_index_for_node_id(st, sid)
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
                lines.append(f"新事件前置时间线（用户指定）：{_event_desc(prev_id)}")
            if next_id:
                lines.append(f"新事件后置时间线（用户指定）：{_event_desc(next_id)}")
            if not prev_id and not next_id:
                lines.append(
                    "新事件未指定时间线前后沿：图谱不自动添加 timeline_next，仅插入时间线列表；"
                    "顺序与因果以本章任务描述为准"
                )
        else:
            lines.append("章节归属时间线：未显式指定（按系统推导/默认流程）")

        if inferred_time_slot:
            lines.append(f"本章时间段（系统推导）：{inferred_time_slot}")

    if pov_ids:
        lines.append(f"主视角候选：{', '.join([x for x in pov_ids if x])}")

    supporting_ids = [str(x).strip() for x in (req.supporting_character_ids or []) if str(x).strip()]
    if supporting_ids:
        lines.append(f"重点涉及角色：{', '.join(supporting_ids)}")

    current_map = str(req.current_map or "").strip()
    if current_map:
        lines.append(f"当前地图：{current_map}")

    lore_tags = [str(x).strip() for x in (req.lore_tags or []) if str(x).strip()]
    if lore_tags:
        lines.append(f"设定标签（lore_tags）：{', '.join(lore_tags)}")

    sd = req.shadow_director_guidance if isinstance(req.shadow_director_guidance, dict) else None
    if sd:
        conflict_type = str(sd.get("conflict_type") or "").strip()
        foreshadow_target = str(sd.get("foreshadow_target") or "").strip()
        supporting_rows = sd.get("supporting_characters")
        if conflict_type:
            lines.append(f"影子编导推荐冲突类型：{conflict_type}")
        if foreshadow_target:
            lines.append(f"影子编导推荐伏笔回收：{foreshadow_target}")
        if isinstance(supporting_rows, list):
            sids: List[str] = []
            for item in supporting_rows:
                if not isinstance(item, dict):
                    continue
                sid = str(item.get("id") or "").strip()
                if sid:
                    sids.append(sid)
            if sids:
                lines.append(f"影子编导推荐配角：{', '.join(sids)}")

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
    - 若已选择章节归属事件，仅更新 state 中的时间线插入逻辑（不按章号写 timeline）
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
        st, inserted_eid = apply_chapter_event_selection(st, chapter_index, req)
        save_state(novel_id, st)
        if inserted_eid:
            patch_new_event_timeline_next_edges(
                novel_id,
                inserted_eid,
                new_event_prev_id=req.new_event_prev_id,
                new_event_next_id=req.new_event_next_id,
            )
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
            "goals": list(c.goals or []),
            "known_facts": list(c.known_facts or []),
        }
    for cid in major_chars:
        char_map.setdefault(
            cid,
            {
                "character_id": cid,
                "description": None,
                "goals": [],
                "known_facts": [],
            },
        )
    save_character_entities(novel_id, list(char_map.values()))

    save_event_rows(
        novel_id,
        [
            {
                "event_id": (ev.event_id or ""),
                "time_slot": str(ev.time_slot or "").strip(),
                "summary": str(ev.summary or "").strip(),
            }
            for ev in (st.world.timeline or [])
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
