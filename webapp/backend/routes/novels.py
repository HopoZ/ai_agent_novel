from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from agents.novel import NovelAgent
from agents.persistence.graph_tables import (
    ensure_graph_tables,
    load_character_entities,
    patch_new_event_timeline_next_edges,
    persist_chapter_artifacts,
    replace_timeline_next_edges_from_state,
    resolve_chapter_timeline_event_id,
    validate_timeline_event_id,
)
from agents.persistence.storage import load_chapter, load_state, save_state, list_chapters
from agents.state.chapter_structure import build_locked_structure_card, evaluate_structure_gate
from agents.state.consistency_audit import build_consistency_audit
from agents.state.state_models import ChapterPlan, ChapterRecord
from webapp.backend.deps import agent, logger
from webapp.backend.paths import STORAGE_NOVELS_DIR
from webapp.backend.run_helpers import (
    apply_chapter_event_selection,
    build_llm_user_task,
    infer_time_slot,
    llm_call_options,
    prebuild_chapter_graph_records,
    req_timeline_focus_id,
    uses_new_timeline_event_for_chapter,
)
from webapp.backend.schemas import (
    CreateNovelRequest,
    RunModeRequest,
)
from webapp.backend.sse import sse_pack

router = APIRouter(tags=["novels"])


def _sync_after_run_if_event(novel_id: str, req: RunModeRequest, chapter_index: Optional[int]) -> None:
    if req.mode not in {"plan_only", "write_chapter", "revise_chapter", "expand_chapter"} or chapter_index is None:
        return
    has_event_selection = bool(
        (req.existing_event_id or "").strip()
        or ((req.new_event_time_slot or "").strip() and (req.new_event_summary or "").strip())
    )
    if not has_event_selection:
        return
    st_now = load_state(novel_id)
    if st_now:
        st_now, inserted_eid = apply_chapter_event_selection(st_now, int(chapter_index), req)
        save_state(novel_id, st_now)
        ensure_graph_tables(novel_id)
        if inserted_eid:
            patch_new_event_timeline_next_edges(
                novel_id,
                inserted_eid,
                new_event_prev_id=req.new_event_prev_id,
                new_event_next_id=req.new_event_next_id,
            )
        replace_timeline_next_edges_from_state(novel_id, st_now)


def _build_structure_gate(
    *,
    novel_id: str,
    req: RunModeRequest,
    inferred_time_slot: Optional[str],
    chapter_index: int,
    timeline_focus_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    if req.mode not in {"plan_only", "write_chapter", "revise_chapter", "expand_chapter"}:
        return None
    st = load_state(novel_id)
    if not st:
        return None
    card = build_locked_structure_card(
        state=st,
        user_task=req.user_task,
        chapter_index=chapter_index,
        inferred_time_slot=inferred_time_slot,
        timeline_event_focus_id=timeline_focus_id,
        req_existing_event_id=req.existing_event_id,
        req_new_event_time_slot=req.new_event_time_slot,
        req_new_event_summary=req.new_event_summary,
        existing_card=(req.structure_card if isinstance(req.structure_card, dict) else None),
    )
    return evaluate_structure_gate(card)


@router.get("")
def list_novels():
    base = STORAGE_NOVELS_DIR
    if not base.exists():
        return {"novels": []}

    novels: List[Dict[str, Any]] = []
    for d in base.iterdir():
        if not d.is_dir():
            continue
        novel_id = d.name
        try:
            state = load_state(novel_id)
            if not state:
                continue
            title = state.meta.novel_title or "未命名小说"
            novels.append(
                {
                    "novel_id": novel_id,
                    "novel_title": title,
                    "initialized": state.meta.initialized,
                    "updated_at": state.meta.updated_at.isoformat(),
                }
            )
        except Exception:
            continue

    novels.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return {"novels": novels}


@router.post("")
def create_novel(req: CreateNovelRequest):
    novel_id = str(uuid4())
    agent.create_novel_stub(
        novel_id=novel_id,
        novel_title=req.novel_title,
        start_time_slot=req.start_time_slot,
        pov_character_id=req.pov_character_id,
        lore_tags=req.lore_tags,
    )

    if req.initial_user_task and req.initial_user_task.strip():
        try:
            agent.init_state(
                novel_id=novel_id,
                user_task=req.initial_user_task,
                lore_tags=req.lore_tags,
            )
        except Exception:
            pass

    return {"novel_id": novel_id}


@router.get("/{novel_id}/state")
def get_state(novel_id: str):
    state = load_state(novel_id)
    if not state:
        raise HTTPException(status_code=404, detail="novel not found")
    return state.model_dump(mode="json")


@router.get("/{novel_id}/character_entities")
def get_character_entities(novel_id: str):
    """人物实体表：供前端主视角/配角等多选候选项。`display_name` 来自 NovelState.characters[].name（或回退为 id）。"""
    st = load_state(novel_id)
    if not st:
        raise HTTPException(status_code=404, detail="novel not found")
    ensure_graph_tables(novel_id)
    rows = load_character_entities(novel_id)
    id_to_label: Dict[str, str] = {}
    for c in st.characters or []:
        cid = str(getattr(c, "character_id", "") or "").strip()
        if not cid:
            continue
        nm = str(getattr(c, "name", None) or "").strip()
        id_to_label[cid] = nm or cid
    enriched: List[Dict[str, Any]] = []
    for r in rows:
        cid = str(r.get("character_id") or "").strip()
        if not cid:
            continue
        row = dict(r)
        row["display_name"] = id_to_label.get(cid, cid)
        enriched.append(row)
    ids = [str(r.get("character_id") or "").strip() for r in rows if str(r.get("character_id") or "").strip()]
    labels = [id_to_label.get(cid, cid) for cid in ids]
    return {
        "novel_id": novel_id,
        "characters": enriched,
        "character_ids": ids,
        "character_labels": labels,
    }


@router.get("/{novel_id}/chapters/{chapter_index}")
def get_chapter(novel_id: str, chapter_index: int):
    chapter = load_chapter(novel_id, chapter_index)
    if not chapter:
        raise HTTPException(status_code=404, detail="chapter not found")
    return chapter.model_dump(mode="json")


@router.get("/{novel_id}/anchors")
def list_event_anchors(novel_id: str):
    state = load_state(novel_id)
    if not state:
        raise HTTPException(status_code=404, detail="novel not found")

    anchors: List[Dict[str, Any]] = []
    for ev in state.world.timeline or []:
        eid = (ev.event_id or "").strip()
        if not eid:
            continue
        anchors.append(
            {
                "id": eid,
                "type": "timeline_event",
                "label": f"{ev.time_slot}：{ev.summary}",
                "time_slot": ev.time_slot,
            }
        )

    for chap in list_chapters(novel_id):
        anchors.append(
            {
                "id": f"ev:chapter:{chap.chapter_index}",
                "type": "chapter_event",
                "label": f"章节事件 · {chap.time_slot}",
                "time_slot": chap.time_slot,
            }
        )

    anchors.sort(key=lambda x: (x.get("time_slot") or ""), reverse=True)
    return {"novel_id": novel_id, "anchors": anchors, "count": len(anchors)}


@router.post("/{novel_id}/run")
def run_mode(novel_id: str, req: RunModeRequest) -> Dict[str, Any]:
    inferred = infer_time_slot(novel_id, req)
    timeline_focus_id = req_timeline_focus_id(req)
    manual_time_slot = bool((req.time_slot_override or "").strip())
    pov_ids = list(req.pov_character_ids_override or [])
    if (not pov_ids) and req.pov_character_id_override:
        pov_ids = [req.pov_character_id_override]
    llm_user_task = build_llm_user_task(novel_id, req.user_task, req, inferred, pov_ids)
    st0 = load_state(novel_id)
    pre_chapter_index = req.chapter_index or ((st0.meta.current_chapter_index + 1) if st0 else 1)
    structure_gate = _build_structure_gate(
        novel_id=novel_id,
        req=req,
        inferred_time_slot=inferred,
        chapter_index=int(pre_chapter_index),
        timeline_focus_id=timeline_focus_id,
    )
    if structure_gate and structure_gate.get("needs_ack") and (not req.structure_risk_ack):
        return {
            "novel_id": novel_id,
            "mode": req.mode,
            "chapter_index": int(pre_chapter_index),
            "state_updated": False,
            "blocked": True,
            "block_type": "structure_gate",
            "structure_gate": structure_gate,
        }
    if req.mode in {"plan_only", "write_chapter", "revise_chapter", "expand_chapter"}:
        try:
            prebuild_chapter_graph_records(
                novel_id=novel_id,
                req=req,
                chapter_index=int(pre_chapter_index),
                inferred_time_slot=inferred,
                pov_ids=pov_ids,
            )
        except Exception as e:
            logger.warning("prebuild chapter graph records failed: %s", e)

    try:
        result = agent.run(
            novel_id=novel_id,
            mode=req.mode,
            user_task=llm_user_task,
            chapter_index=req.chapter_index,
            chapter_preset_name=req.chapter_preset_name,
            time_slot_override=inferred,
            manual_time_slot=manual_time_slot,
            pov_character_ids_override=pov_ids,
            supporting_character_ids=(req.supporting_character_ids or []),
            lore_tags=req.lore_tags,
            llm_options=llm_call_options(req),
            timeline_event_focus_id=timeline_focus_id,
            omit_world_timeline=uses_new_timeline_event_for_chapter(req),
            structure_card=(structure_gate.get("card") if structure_gate else None),
            structure_card_locked=bool(structure_gate),
        )
    except Exception as e:
        logger.exception("run_mode failed novel_id=%s mode=%s", novel_id, req.mode)
        raise HTTPException(status_code=400, detail=str(e))

    _sync_after_run_if_event(novel_id, req, result.chapter_index)

    resp: Dict[str, Any] = {
        "novel_id": novel_id,
        "mode": req.mode,
        "chapter_index": result.chapter_index,
        "state_updated": result.state_updated,
        "usage_metadata": result.usage_metadata,
    }
    if result.content:
        resp["content"] = result.content
    if result.plan:
        resp["plan"] = result.plan.model_dump(mode="json")
    if result.next_status:
        resp["next_status"] = result.next_status
    if structure_gate:
        resp["structure_gate"] = structure_gate
    state_obj = load_state(novel_id)
    resp["state"] = state_obj.model_dump(mode="json") if state_obj else None
    if req.mode in {"write_chapter", "revise_chapter", "expand_chapter"} and result.chapter_index and state_obj:
        chapter_row = load_chapter(novel_id, int(result.chapter_index))
        if chapter_row:
            resp["consistency_audit"] = build_consistency_audit(
                state=state_obj,
                chapter=chapter_row,
                mode=req.mode,
            )
    return resp


@router.post("/{novel_id}/preview_input")
def preview_mode_input(novel_id: str, req: RunModeRequest) -> Dict[str, Any]:
    inferred = infer_time_slot(novel_id, req)
    timeline_focus_id = req_timeline_focus_id(req)
    manual_time_slot = bool((req.time_slot_override or "").strip())
    pov_ids = list(req.pov_character_ids_override or [])
    if (not pov_ids) and req.pov_character_id_override:
        pov_ids = [req.pov_character_id_override]
    llm_user_task = build_llm_user_task(novel_id, req.user_task, req, inferred, pov_ids)
    st0 = load_state(novel_id)
    pre_chapter_index = req.chapter_index or ((st0.meta.current_chapter_index + 1) if st0 else 1)
    try:
        out = agent.preview_input(
            novel_id=novel_id,
            mode=req.mode,
            user_task=llm_user_task,
            chapter_index=req.chapter_index,
            time_slot_override=inferred,
            manual_time_slot=manual_time_slot,
            pov_character_ids_override=pov_ids,
            supporting_character_ids=(req.supporting_character_ids or []),
            lore_tags=req.lore_tags,
            timeline_event_focus_id=timeline_focus_id,
            omit_world_timeline=uses_new_timeline_event_for_chapter(req),
        )
        structure_gate = _build_structure_gate(
            novel_id=novel_id,
            req=req,
            inferred_time_slot=inferred,
            chapter_index=int(pre_chapter_index),
            timeline_focus_id=timeline_focus_id,
        )
        if structure_gate:
            out["structure_gate"] = structure_gate
        return out
    except Exception as e:
        logger.exception("preview_input failed novel_id=%s mode=%s", novel_id, req.mode)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{novel_id}/run_stream")
def run_mode_stream(novel_id: str, req: RunModeRequest, request: Request):
    async def gen():
        async def _disconnected() -> bool:
            try:
                return await request.is_disconnected()
            except Exception:
                return False

        yield sse_pack("start", {"novel_id": novel_id, "mode": req.mode})

        inferred = infer_time_slot(novel_id, req)
        timeline_focus_id = req_timeline_focus_id(req)
        manual_time_slot = bool((req.time_slot_override or "").strip())
        pov_ids = list(req.pov_character_ids_override or [])
        if (not pov_ids) and req.pov_character_id_override:
            pov_ids = [req.pov_character_id_override]
        llm_user_task = build_llm_user_task(novel_id, req.user_task, req, inferred, pov_ids)
        llm_opts = llm_call_options(req)
        omit_world_timeline = uses_new_timeline_event_for_chapter(req)
        st0 = load_state(novel_id)
        pre_chapter_index = req.chapter_index or ((st0.meta.current_chapter_index + 1) if st0 else 1)
        structure_gate = _build_structure_gate(
            novel_id=novel_id,
            req=req,
            inferred_time_slot=inferred,
            chapter_index=int(pre_chapter_index),
            timeline_focus_id=timeline_focus_id,
        )
        if structure_gate and structure_gate.get("needs_ack") and (not req.structure_risk_ack):
            yield sse_pack(
                "done",
                {
                    "novel_id": novel_id,
                    "mode": req.mode,
                    "chapter_index": int(pre_chapter_index),
                    "state_updated": False,
                    "blocked": True,
                    "block_type": "structure_gate",
                    "structure_gate": structure_gate,
                    "usage_metadata": {},
                    "content": None,
                    "plan": None,
                    "state": (st0.model_dump(mode="json") if st0 else None),
                    "next_status": None,
                },
            )
            return

        try:
            if req.mode in {"write_chapter", "revise_chapter", "expand_chapter"}:
                if await _disconnected():
                    logger.info("run_stream client disconnected early. novel_id=%s mode=%s", novel_id, req.mode)
                    return
                yield sse_pack("phase", {"name": "planning"})

                st = load_state(novel_id)
                if not st:
                    raise ValueError("novel not found")
                if not st.meta.initialized:
                    raise ValueError("state not initialized. please run init_state first")

                chapter_index = req.chapter_index or (st.meta.current_chapter_index + 1)
                try:
                    prebuild_chapter_graph_records(
                        novel_id=novel_id,
                        req=req,
                        chapter_index=int(chapter_index),
                        inferred_time_slot=inferred,
                        pov_ids=pov_ids,
                    )
                except Exception as e:
                    logger.warning("prebuild chapter graph records failed(stream): %s", e)
                plan_json: Optional[Dict[str, Any]] = None
                for item in agent.plan_chapter_stream(
                    novel_id=novel_id,
                    user_task=llm_user_task,
                    chapter_index=chapter_index,
                    time_slot_override=inferred,
                    pov_character_ids_override=pov_ids,
                    supporting_character_ids=(req.supporting_character_ids or []),
                    minimal_state_for_prompt=manual_time_slot,
                    lore_tags=req.lore_tags,
                    llm_options=llm_opts,
                    timeline_event_focus_id=timeline_focus_id,
                    omit_world_timeline=omit_world_timeline,
                ):
                    if await _disconnected():
                        logger.info(
                            "run_stream disconnected during plan stream. novel_id=%s chapter=%s",
                            novel_id,
                            chapter_index,
                        )
                        return
                    txt = str(item.get("delta", "") or "")
                    if txt:
                        yield sse_pack("plan_content", {"delta": txt})
                    if item.get("done"):
                        plan_json = item.get("plan") or {}
                if not plan_json:
                    raise ValueError("plan stream failed: empty plan")
                plan = ChapterPlan.model_validate(plan_json)
                try:
                    plan.next_state = NovelAgent.merge_state(st, plan.next_state)  # type: ignore
                except Exception as e:
                    logger.warning("merge_state failed in stream save: %s", e)
                plan.next_state, inserted_timeline_eid = apply_chapter_event_selection(
                    plan.next_state, chapter_index, req
                )

                yield sse_pack("phase", {"name": "writing", "chapter_index": chapter_index})
                parts: List[str] = []
                usage_meta: Dict[str, Any] = {}
                write_mode = "expand" if req.mode == "expand_chapter" else "generate"
                for item in agent.write_chapter_text_stream(
                    novel_id=novel_id,
                    plan=plan,
                    user_task=llm_user_task,
                    minimal_state_for_prompt=manual_time_slot,
                    lore_tags=req.lore_tags,
                    time_slot_hint=inferred,
                    pov_character_ids_override=pov_ids,
                    supporting_character_ids=(req.supporting_character_ids or []),
                    llm_options=llm_opts,
                    timeline_event_focus_id=timeline_focus_id,
                    write_mode=write_mode,
                    omit_world_timeline=omit_world_timeline,
                ):
                    if await _disconnected():
                        logger.info(
                            "run_stream disconnected during write stream. novel_id=%s chapter=%s",
                            novel_id,
                            chapter_index,
                        )
                        return
                    txt = str(item.get("delta", "") or "")
                    if txt:
                        parts.append(txt)
                        yield sse_pack("content", {"delta": txt})
                    um = item.get("usage_metadata") or {}
                    if isinstance(um, dict) and um:
                        usage_meta = um

                content_text = "".join(parts).strip()

                if await _disconnected():
                    logger.info(
                        "run_stream disconnected before saving. novel_id=%s chapter=%s",
                        novel_id,
                        chapter_index,
                    )
                    return
                yield sse_pack("phase", {"name": "saving"})
                next_state = plan.next_state
                record = ChapterRecord(
                    chapter_index=chapter_index,
                    chapter_preset_name=req.chapter_preset_name,
                    timeline_event_id=validate_timeline_event_id(next_state, timeline_focus_id),
                    time_slot=plan.time_slot,
                    pov_character_id=plan.pov_character_id,
                    who_is_present=plan.who_is_present,
                    beats=plan.beats,
                    content=content_text,
                    usage_metadata=usage_meta,
                    structure_card=(structure_gate.get("card") if structure_gate else {}),
                    structure_card_locked=bool(structure_gate),
                )
                persist_chapter_artifacts(
                    novel_id=novel_id,
                    chapter=record,
                    next_state=next_state,
                    chapter_preset_name=req.chapter_preset_name,
                    new_timeline_event_id=inserted_timeline_eid,
                    new_event_prev_id=req.new_event_prev_id,
                    new_event_next_id=req.new_event_next_id,
                )

                try:
                    from agents.text_utils import write_outputs_txt

                    title = (st.meta.novel_title or "未命名小说") if st else "未命名小说"
                    out_path = write_outputs_txt(title, chapter_index, content_text)
                    yield sse_pack("phase", {"name": "outputs_written", "path": out_path})
                except Exception as e:
                    logger.warning("Failed to write outputs txt (stream): %s", e)
                    yield sse_pack("phase", {"name": "outputs_write_failed", "error": str(e)})

                next_status = ""
                try:
                    if await _disconnected():
                        logger.info(
                            "run_stream disconnected before next_status. novel_id=%s chapter=%s",
                            novel_id,
                            chapter_index,
                        )
                        return
                    yield sse_pack("phase", {"name": "next_status"})
                    next_status = agent.suggest_next_status(
                        novel_id=novel_id,
                        user_task=llm_user_task,
                        chapter_index=chapter_index,
                        latest_content=content_text,
                        llm_options=llm_opts,
                        timeline_event_focus_id=timeline_focus_id,
                    )
                    yield sse_pack("phase", {"name": "next_status_done", "has_text": bool((next_status or "").strip())})
                except Exception as e:
                    logger.warning("Failed to generate next_status (stream): %s", e)
                    yield sse_pack("phase", {"name": "next_status_failed", "error": str(e)})

                st_done = load_state(novel_id)
                chapter_timeline_event_id = (
                    resolve_chapter_timeline_event_id(st_done, record) if st_done else None
                )
                consistency_audit = (
                    build_consistency_audit(state=st_done, chapter=record, mode=req.mode)
                    if st_done
                    else None
                )

                yield sse_pack(
                    "done",
                    {
                        "novel_id": novel_id,
                        "mode": req.mode,
                        "chapter_index": chapter_index,
                        "state_updated": True,
                        "usage_metadata": usage_meta,
                        "plan": plan.model_dump(mode="json"),
                        "state": (st_done.model_dump(mode="json") if st_done else None),
                        "next_status": next_status or None,
                        "chapter_timeline_event_id": chapter_timeline_event_id,
                        "consistency_audit": consistency_audit,
                        "structure_gate": structure_gate,
                    },
                )
            elif req.mode == "optimize_suggestions":
                if await _disconnected():
                    return
                st_opt = load_state(novel_id)
                if not st_opt or not st_opt.meta.initialized:
                    raise ValueError("state not initialized. please run init_state first")
                yield sse_pack("phase", {"name": "optimizing"})
                opt_parts: List[str] = []
                opt_usage: Dict[str, Any] = {}
                for item in agent.optimize_suggestions_stream(
                    novel_id=novel_id,
                    user_task=llm_user_task,
                    lore_tags=req.lore_tags,
                    llm_options=llm_opts,
                ):
                    if await _disconnected():
                        return
                    txt = str(item.get("delta", "") or "")
                    if txt:
                        opt_parts.append(txt)
                        yield sse_pack("content", {"delta": txt})
                    um = item.get("usage_metadata") or {}
                    if isinstance(um, dict) and um:
                        opt_usage = um
                st_final = load_state(novel_id)
                yield sse_pack(
                    "done",
                    {
                        "novel_id": novel_id,
                        "mode": req.mode,
                        "chapter_index": None,
                        "state_updated": False,
                        "usage_metadata": opt_usage,
                        "content": "".join(opt_parts).strip(),
                        "plan": None,
                        "state": (st_final.model_dump(mode="json") if st_final else None),
                        "next_status": None,
                    },
                )
            elif req.mode == "init_state":
                if await _disconnected():
                    return
                yield sse_pack("phase", {"name": "world_init"})
                state_dump: Optional[Dict[str, Any]] = None
                init_usage: Dict[str, Any] = {}
                for item in agent.init_state_stream(
                    novel_id=novel_id,
                    user_task=llm_user_task,
                    lore_tags=req.lore_tags,
                    llm_options=llm_opts,
                ):
                    if await _disconnected():
                        return
                    txt = str(item.get("delta", "") or "")
                    if txt:
                        yield sse_pack("content", {"delta": txt})
                    um = item.get("usage_metadata") or {}
                    if isinstance(um, dict) and um:
                        init_usage = um
                    if item.get("done"):
                        state_dump = item.get("state")
                if not state_dump:
                    raise ValueError("init_state stream failed: empty state")
                st_final = load_state(novel_id)
                yield sse_pack(
                    "done",
                    {
                        "novel_id": novel_id,
                        "mode": req.mode,
                        "chapter_index": None,
                        "state_updated": True,
                        "usage_metadata": init_usage,
                        "content": None,
                        "plan": None,
                        "state": (st_final.model_dump(mode="json") if st_final else None),
                        "next_status": None,
                    },
                )
            else:
                if await _disconnected():
                    logger.info(
                        "run_stream disconnected before non-stream run. novel_id=%s mode=%s",
                        novel_id,
                        req.mode,
                    )
                    return
                yield sse_pack("phase", {"name": "running"})
                stx = load_state(novel_id)
                chapter_index = req.chapter_index or ((stx.meta.current_chapter_index + 1) if stx else 1)
                if req.mode != "init_state":
                    try:
                        prebuild_chapter_graph_records(
                            novel_id=novel_id,
                            req=req,
                            chapter_index=int(chapter_index),
                            inferred_time_slot=inferred,
                            pov_ids=pov_ids,
                        )
                    except Exception as e:
                        logger.warning("prebuild chapter graph records failed(non-stream): %s", e)
                result = agent.run(
                    novel_id=novel_id,
                    mode=req.mode,
                    user_task=llm_user_task,
                    chapter_index=req.chapter_index,
                    chapter_preset_name=req.chapter_preset_name,
                    time_slot_override=inferred,
                    manual_time_slot=manual_time_slot,
                    pov_character_ids_override=pov_ids,
                    supporting_character_ids=(req.supporting_character_ids or []),
                    lore_tags=req.lore_tags,
                    llm_options=llm_opts,
                    timeline_event_focus_id=timeline_focus_id,
                    omit_world_timeline=omit_world_timeline,
                    structure_card=(structure_gate.get("card") if structure_gate else None),
                    structure_card_locked=bool(structure_gate),
                )
                _sync_after_run_if_event(novel_id, req, result.chapter_index)
                state_obj = load_state(novel_id)
                consistency_audit = None
                if req.mode in {"write_chapter", "revise_chapter", "expand_chapter"} and result.chapter_index and state_obj:
                    chapter_row = load_chapter(novel_id, int(result.chapter_index))
                    if chapter_row:
                        consistency_audit = build_consistency_audit(
                            state=state_obj,
                            chapter=chapter_row,
                            mode=req.mode,
                        )
                yield sse_pack(
                    "done",
                    {
                        "novel_id": novel_id,
                        "mode": req.mode,
                        "chapter_index": result.chapter_index,
                        "state_updated": result.state_updated,
                        "usage_metadata": result.usage_metadata,
                        "content": result.content,
                        "plan": (result.plan.model_dump(mode="json") if result.plan else None),
                        "state": (state_obj.model_dump(mode="json") if state_obj else None),
                        "consistency_audit": consistency_audit,
                        "structure_gate": structure_gate,
                    },
                )
        except Exception as e:
            logger.exception("run_stream failed novel_id=%s mode=%s", novel_id, req.mode)
            if not await _disconnected():
                yield sse_pack("error", {"message": str(e)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
