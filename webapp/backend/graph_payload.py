"""由 NovelState + 图谱四表拼装 JSON（nodes/edges），供 GET /graph 使用。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from agents.persistence.graph_tables import ensure_graph_tables, load_character_relations, load_event_relations
from agents.persistence.storage import list_chapters
from agents.state.state_models import NovelState


def build_novel_graph_payload(novel_id: str, state: NovelState, view: str) -> Dict[str, Any]:
    """
    view:
      - people: 人物关系网
      - events: 剧情事件网
      - mixed: 混合网
    """
    view = (view or "mixed").lower()
    ensure_graph_tables(novel_id)
    char_relations = load_character_relations(novel_id)
    event_relations = load_event_relations(novel_id)

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    node_ids: Set[str] = set()

    def add_node(node_id: str, label: str, ntype: str, extra: Optional[Dict[str, Any]] = None):
        if not node_id:
            return
        if node_id in node_ids:
            return
        node_ids.add(node_id)
        payload = {"id": node_id, "label": label or node_id, "type": ntype}
        if extra:
            payload.update(extra)
        nodes.append(payload)

    def add_edge(source: str, target: str, label: str = "", etype: str = "rel"):
        if not source or not target:
            return
        edges.append({"source": source, "target": target, "label": label, "type": etype})

    if view in {"people", "mixed"}:
        for c in state.characters:
            cid = c.character_id
            add_node(f"char:{cid}", cid, "character", {"data": c.model_dump(mode="json")})

        for r in char_relations:
            src = str(r.get("source", "")).strip()
            tgt = str(r.get("target", "")).strip()
            if not (src.startswith("char:") and tgt.startswith("char:")):
                continue
            add_node(src, src.split("char:", 1)[1], "character")
            add_node(tgt, tgt.split("char:", 1)[1], "character")
            add_edge(src, tgt, str(r.get("label", "")), "relationship")

    if view in {"events", "mixed"}:
        for idx, ev in enumerate(state.world.timeline or []):
            eid = f"ev:timeline:{idx}"
            label = f"{ev.time_slot}：{ev.summary}"
            add_node(eid, label, "timeline_event", {"data": ev.model_dump(mode="json")})

        for i, r in enumerate(event_relations):
            kind = str(r.get("kind", "")).strip().lower()
            if kind not in {"timeline_next", "appear"}:
                continue
            src = str(r.get("source", "") or "").strip()
            tgt = str(r.get("target", "") or "").strip()
            label = str(r.get("label", "") or ("时间推进" if kind == "timeline_next" else "出场"))
            if kind == "timeline_next":
                if not src:
                    src = f"ev:timeline:draft_src:{i}"
                    add_node(src, "（待定起点）", "timeline_event", {"data": {"time_slot": "待定", "summary": "待完善"}})
                if not tgt:
                    tgt = f"ev:timeline:draft_tgt:{i}"
                    add_node(tgt, "（待定终点）", "timeline_event", {"data": {"time_slot": "待定", "summary": "待完善"}})
                add_edge(src, tgt, label, "timeline_next")
            elif kind == "appear" and view == "mixed":
                if src and src.startswith("char:"):
                    add_node(src, src.split("char:", 1)[1], "character")
                if tgt and tgt.startswith("ev:chapter:"):
                    add_edge(src, tgt, label, "appear")

        for chap in list_chapters(novel_id):
            cid = f"ev:chapter:{chap.chapter_index}"
            label = f"章节事件 · {chap.time_slot}"
            add_node(cid, label, "chapter_event", {"data": chap.model_dump(mode="json")})

            timeline_idx = -1
            for ti, ev in enumerate(state.world.timeline or []):
                if ev.chapter_index == chap.chapter_index:
                    timeline_idx = ti
                    break
            if timeline_idx < 0:
                ts = str(chap.time_slot or "").strip()
                for ti, ev in enumerate(state.world.timeline or []):
                    if str(ev.time_slot or "").strip() == ts:
                        timeline_idx = ti
                        break
            if timeline_idx >= 0:
                add_edge(cid, f"ev:timeline:{timeline_idx}", "属于事件", "chapter_belongs")

    if view == "mixed":
        for fname, fdesc in (state.world.factions or {}).items():
            fid = f"fac:{fname}"
            add_node(fid, fname, "faction", {"data": {"description": fdesc}})

    return {"view": view, "nodes": nodes, "edges": edges}
