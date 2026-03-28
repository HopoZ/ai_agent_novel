from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from agents.persistence.graph_tables import (
    ensure_graph_tables,
    load_character_relations,
    load_event_relations,
    remap_timeline_numeric_edges_after_delete,
    replace_timeline_next_edges_from_state,
    save_character_entities,
    save_character_relations,
    save_event_relations,
    sync_timeline_event_entity_rows,
)
from agents.persistence.storage import load_state, save_state
from agents.state.state_models import CharacterState, TimelineEvent
from webapp.backend.deps import logger
from webapp.backend.graph_payload import build_novel_graph_payload
from webapp.backend.schemas import (
    GraphEdgePatchRequest,
    GraphNodeCreateRequest,
    GraphNodePatchRequest,
    GraphRelationshipRequest,
    TimelineNeighborsRequest,
)

router = APIRouter(tags=["graph"])


@router.get("/{novel_id}/graph")
def get_novel_graph(novel_id: str, view: str = "mixed"):
    state = load_state(novel_id)
    if not state:
        raise HTTPException(status_code=404, detail="novel not found")

    view_norm = (view or "mixed").lower()
    if view_norm not in {"people", "events", "mixed"}:
        raise HTTPException(status_code=400, detail="view must be one of: people, events, mixed")

    return build_novel_graph_payload(novel_id, state, view_norm)


@router.patch("/{novel_id}/graph/node")
def patch_graph_node(novel_id: str, req: GraphNodePatchRequest):
    state = load_state(novel_id)
    if not state:
        raise HTTPException(status_code=404, detail="novel not found")
    node_id = (req.node_id or "").strip()
    patch = req.patch or {}

    if node_id.startswith("char:"):
        cid = node_id.split("char:", 1)[1].strip()
        hit = None
        for c in state.characters or []:
            if c.character_id == cid:
                hit = c
                break
        if not hit:
            raise HTTPException(status_code=404, detail="character not found")
        if "description" in patch:
            hit.description = str(patch.get("description") or "").strip() or hit.description
        if "current_location" in patch:
            hit.current_location = str(patch.get("current_location") or "").strip() or hit.current_location
        if "goals" in patch:
            v = patch.get("goals")
            if isinstance(v, list):
                hit.goals = [str(x).strip() for x in v if str(x).strip()]
            else:
                txt = str(v or "").strip()
                hit.goals = [s.strip() for s in txt.splitlines() if s.strip()] if txt else []
        if "known_facts" in patch:
            v = patch.get("known_facts")
            if isinstance(v, list):
                hit.known_facts = [str(x).strip() for x in v if str(x).strip()]
            else:
                txt = str(v or "").strip()
                hit.known_facts = [s.strip() for s in txt.splitlines() if s.strip()] if txt else []
        save_state(novel_id, state)
        ensure_graph_tables(novel_id)
        save_character_entities(
            novel_id,
            [
                {
                    "character_id": c.character_id,
                    "description": c.description,
                    "current_location": c.current_location,
                    "alive": c.alive,
                    "goals": list(c.goals or []),
                    "known_facts": list(c.known_facts or []),
                }
                for c in (state.characters or [])
            ],
        )
        return {"ok": True, "node_id": node_id}

    if node_id.startswith("fac:"):
        fname = node_id.split("fac:", 1)[1].strip()
        if not fname:
            raise HTTPException(status_code=400, detail="invalid faction id")
        if state.world.factions is None:
            state.world.factions = {}
        if "description" in patch:
            state.world.factions[fname] = str(patch.get("description") or "").strip()
        save_state(novel_id, state)
        return {"ok": True, "node_id": node_id}

    if node_id.startswith("ev:timeline:"):
        raw = node_id.split("ev:timeline:", 1)[1].strip()
        try:
            idx = int(raw)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid timeline index")
        if not (0 <= idx < len(state.world.timeline or [])):
            raise HTTPException(status_code=404, detail="timeline event not found")
        ev = state.world.timeline[idx]
        if "time_slot" in patch:
            ev.time_slot = str(patch.get("time_slot") or "").strip() or ev.time_slot
        if "summary" in patch:
            ev.summary = str(patch.get("summary") or "").strip() or ev.summary
        save_state(novel_id, state)
        ensure_graph_tables(novel_id)
        sync_timeline_event_entity_rows(novel_id, state)
        replace_timeline_next_edges_from_state(novel_id, state)
        return {"ok": True, "node_id": node_id}

    raise HTTPException(status_code=400, detail="unsupported node_id")


@router.post("/{novel_id}/graph/nodes")
def create_graph_node(novel_id: str, req: GraphNodeCreateRequest):
    state = load_state(novel_id)
    if not state:
        raise HTTPException(status_code=404, detail="novel not found")
    ensure_graph_tables(novel_id)
    nt = (req.node_type or "").strip().lower()

    if nt == "character":
        cid = str(req.character_id or "").strip()
        if not cid:
            raise HTTPException(status_code=400, detail="character_id is required")
        for c in state.characters or []:
            if c.character_id == cid:
                raise HTTPException(status_code=400, detail="character_id already exists")
        state.characters = list(state.characters or [])
        state.characters.append(
            CharacterState(
                character_id=cid,
                description=str(req.description or "").strip() or None,
                current_location=str(req.current_location or "").strip() or None,
                goals=[],
                known_facts=[],
                relationships={},
            )
        )
        save_state(novel_id, state)
        save_character_entities(
            novel_id,
            [
                {
                    "character_id": c.character_id,
                    "description": c.description,
                    "current_location": c.current_location,
                    "alive": c.alive,
                    "goals": list(c.goals or []),
                    "known_facts": list(c.known_facts or []),
                }
                for c in (state.characters or [])
            ],
        )
        return {"ok": True, "node_id": f"char:{cid}"}

    if nt == "timeline_event":
        slot = str(req.time_slot or "").strip()
        summ = str(req.summary or "").strip()
        if not slot or not summ:
            raise HTTPException(status_code=400, detail="time_slot and summary are required")
        tl = list(state.world.timeline or [])
        tl.append(
            TimelineEvent(
                time_slot=slot,
                summary=summ,
                chapter_index=req.chapter_index,
            )
        )
        state.world.timeline = tl
        save_state(novel_id, state)
        sync_timeline_event_entity_rows(novel_id, state)
        replace_timeline_next_edges_from_state(novel_id, state)
        new_idx = len(tl) - 1
        return {"ok": True, "node_id": f"ev:timeline:{new_idx}"}

    if nt == "faction":
        fname = str(req.faction_name or "").strip()
        if not fname:
            raise HTTPException(status_code=400, detail="faction_name is required")
        if state.world.factions is None:
            state.world.factions = {}
        if fname in state.world.factions:
            raise HTTPException(status_code=400, detail="faction_name already exists")
        state.world.factions[fname] = str(req.description or "").strip()
        save_state(novel_id, state)
        return {"ok": True, "node_id": f"fac:{fname}"}

    raise HTTPException(status_code=400, detail="node_type must be character | timeline_event | faction")


@router.delete("/{novel_id}/graph/nodes")
def delete_graph_node(novel_id: str, node_id: str = Query(..., description="char:* | ev:timeline:N | fac:*")):
    state = load_state(novel_id)
    if not state:
        raise HTTPException(status_code=404, detail="novel not found")
    ensure_graph_tables(novel_id)
    nid = (node_id or "").strip()

    if nid.startswith("ev:chapter:"):
        raise HTTPException(status_code=400, detail="章节节点来自已保存章节，请使用章节管理删除正文（当前未提供图谱内删除）")

    if nid.startswith("char:"):
        cid = nid.split("char:", 1)[1].strip()
        if not cid:
            raise HTTPException(status_code=400, detail="invalid character id")
        before = len(state.characters or [])
        state.characters = [c for c in (state.characters or []) if c.character_id != cid]
        if len(state.characters) == before:
            raise HTTPException(status_code=404, detail="character not found")
        for c in state.characters or []:
            c.relationships = {k: v for k, v in (c.relationships or {}).items() if k != cid}
        wp = state.continuity.who_is_present or []
        state.continuity.who_is_present = [p for p in wp if p.character_id != cid]
        if (state.continuity.pov_character_id or "") == cid:
            state.continuity.pov_character_id = None
        crows = load_character_relations(novel_id)
        crows = [
            r
            for r in crows
            if not (
                str(r.get("kind", "")).strip().lower() == "relationship"
                and (
                    str(r.get("source", "")).strip() == nid
                    or str(r.get("target", "")).strip() == nid
                )
            )
        ]
        save_character_relations(novel_id, crows)
        erows = load_event_relations(novel_id)
        erows = [
            r
            for r in erows
            if not (
                str(r.get("kind", "")).strip().lower() == "appear"
                and str(r.get("source", "")).strip() == nid
            )
        ]
        save_event_relations(novel_id, erows)
        save_state(novel_id, state)
        save_character_entities(
            novel_id,
            [
                {
                    "character_id": c.character_id,
                    "description": c.description,
                    "current_location": c.current_location,
                    "alive": c.alive,
                    "goals": list(c.goals or []),
                    "known_facts": list(c.known_facts or []),
                }
                for c in (state.characters or [])
            ],
        )
        return {"ok": True, "node_id": nid}

    if nid.startswith("fac:"):
        fname = nid.split("fac:", 1)[1].strip()
        if not fname or state.world.factions is None or fname not in state.world.factions:
            raise HTTPException(status_code=404, detail="faction not found")
        del state.world.factions[fname]
        save_state(novel_id, state)
        return {"ok": True, "node_id": nid}

    if nid.startswith("ev:timeline:"):
        raw = nid.split("ev:timeline:", 1)[1].strip()
        if not raw.isdigit():
            raise HTTPException(status_code=400, detail="只能删除正式时间线索引节点（非草稿 id）")
        try:
            idx = int(raw)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid timeline index")
        tl = list(state.world.timeline or [])
        if not (0 <= idx < len(tl)):
            raise HTTPException(status_code=404, detail="timeline event not found")
        tl.pop(idx)
        state.world.timeline = tl
        er = load_event_relations(novel_id)
        er = remap_timeline_numeric_edges_after_delete(er, idx)
        save_event_relations(novel_id, er)
        save_state(novel_id, state)
        sync_timeline_event_entity_rows(novel_id, state)
        replace_timeline_next_edges_from_state(novel_id, state)
        return {"ok": True, "node_id": nid}

    raise HTTPException(status_code=400, detail="unsupported node_id")


@router.post("/{novel_id}/graph/relationship")
def upsert_graph_relationship(novel_id: str, req: GraphRelationshipRequest):
    state = load_state(novel_id)
    if not state:
        raise HTTPException(status_code=404, detail="novel not found")
    ensure_graph_tables(novel_id)
    src = (req.source or "").strip()
    tgt = (req.target or "").strip()
    if (not src.startswith("char:")) or (not tgt.startswith("char:")):
        raise HTTPException(status_code=400, detail="source/target must be char:{id}")

    op = (req.op or "set").strip().lower()
    label = str(req.label or "").strip()
    rows = load_character_relations(novel_id)
    rows = [
        r
        for r in rows
        if not (
            str(r.get("kind", "")).strip().lower() == "relationship"
            and str(r.get("source", "")).strip() == src
            and str(r.get("target", "")).strip() == tgt
        )
    ]
    if op != "delete":
        if not label:
            raise HTTPException(status_code=400, detail="label is required for set")
        rows.append({"source": src, "target": tgt, "label": label, "kind": "relationship"})
    save_character_relations(novel_id, rows)
    return {"ok": True}


@router.patch("/{novel_id}/graph/timeline-neighbors")
def patch_timeline_neighbors(novel_id: str, req: TimelineNeighborsRequest):
    state = load_state(novel_id)
    if not state:
        raise HTTPException(status_code=404, detail="novel not found")
    ensure_graph_tables(novel_id)

    node_id = (req.node_id or "").strip()
    if not node_id.startswith("ev:timeline:"):
        raise HTTPException(status_code=400, detail="node_id must be ev:timeline:*")
    prev_source = (req.prev_source or "").strip()
    next_target = (req.next_target or "").strip()

    def _must_timeline_ref(label: str, v: str) -> None:
        if not v.startswith("ev:timeline:"):
            raise HTTPException(status_code=400, detail=f"{label} must be ev:timeline:* when set")
        if v == node_id:
            raise HTTPException(status_code=400, detail=f"{label} cannot equal node_id")

    if prev_source:
        _must_timeline_ref("prev_source", prev_source)
    if next_target:
        _must_timeline_ref("next_target", next_target)

    rows = load_event_relations(novel_id)
    rows = [
        r
        for r in rows
        if not (
            str(r.get("kind", "")).strip().lower() == "timeline_next"
            and (str(r.get("source", "")).strip() == node_id or str(r.get("target", "")).strip() == node_id)
        )
    ]
    if prev_source:
        rows.append({"source": prev_source, "target": node_id, "label": "时间推进", "kind": "timeline_next"})
    if next_target:
        rows.append({"source": node_id, "target": next_target, "label": "时间推进", "kind": "timeline_next"})
    save_event_relations(novel_id, rows)
    logger.info(
        "patch_timeline_neighbors novel_id=%s node_id=%s prev_source=%r next_target=%r",
        novel_id,
        node_id,
        prev_source,
        next_target,
    )
    return {"ok": True}


@router.patch("/{novel_id}/graph/edge")
def patch_graph_edge(novel_id: str, req: GraphEdgePatchRequest):
    state = load_state(novel_id)
    if not state:
        raise HTTPException(status_code=404, detail="novel not found")
    ensure_graph_tables(novel_id)

    et = (req.edge_type or "").strip().lower()
    src = (req.source or "").strip()
    tgt = (req.target or "").strip()
    nsrc = (req.new_source or src).strip()
    ntgt = (req.new_target or tgt).strip()
    op = (req.op or "set").strip().lower()
    label = (req.label or "").strip()

    if et == "relationship":
        if not (
            src.startswith("char:")
            and tgt.startswith("char:")
            and nsrc.startswith("char:")
            and ntgt.startswith("char:")
        ):
            raise HTTPException(status_code=400, detail="relationship requires char:* -> char:*")
        rows = load_character_relations(novel_id)
        rows = [
            r
            for r in rows
            if not (
                str(r.get("kind", "")).strip().lower() == "relationship"
                and str(r.get("source", "")).strip() == src
                and str(r.get("target", "")).strip() == tgt
            )
        ]
        if op != "delete":
            if not label:
                raise HTTPException(status_code=400, detail="label is required for relationship set")
            rows.append({"source": nsrc, "target": ntgt, "label": label, "kind": "relationship"})
        save_character_relations(novel_id, rows)
        return {"ok": True}

    if et in {"appear", "timeline_next"}:
        rows = load_event_relations(novel_id)
        rows = [
            r
            for r in rows
            if not (
                str(r.get("kind", "")).strip().lower() == et
                and str(r.get("source", "")).strip() == src
                and str(r.get("target", "")).strip() == tgt
            )
        ]
        if op != "delete":
            rows.append(
                {
                    "source": nsrc,
                    "target": ntgt,
                    "label": (label or ("待完善" if (et == "timeline_next" and (not nsrc or not ntgt)) else "")),
                    "kind": et,
                }
            )
        save_event_relations(novel_id, rows)
        return {"ok": True}

    if et == "chapter_belongs":
        if not nsrc.startswith("ev:chapter:"):
            raise HTTPException(status_code=400, detail="chapter_belongs source must be ev:chapter:*")
        try:
            chap_idx = int(nsrc.split("ev:chapter:", 1)[1].strip())
        except Exception:
            raise HTTPException(status_code=400, detail="invalid chapter source")

        for ev in state.world.timeline or []:
            if ev.chapter_index == chap_idx:
                ev.chapter_index = None

        if op != "delete" and ntgt:
            if not ntgt.startswith("ev:timeline:"):
                raise HTTPException(status_code=400, detail="chapter_belongs target must be ev:timeline:* or empty")
            try:
                t_idx = int(ntgt.split("ev:timeline:", 1)[1].strip())
            except Exception:
                raise HTTPException(status_code=400, detail="invalid timeline target")
            if not (0 <= t_idx < len(state.world.timeline or [])):
                raise HTTPException(status_code=404, detail="timeline event not found")
            state.world.timeline[t_idx].chapter_index = chap_idx

        save_state(novel_id, state)
        sync_timeline_event_entity_rows(novel_id, state)
        replace_timeline_next_edges_from_state(novel_id, state)
        return {"ok": True}

    raise HTTPException(status_code=400, detail="unsupported edge_type")
