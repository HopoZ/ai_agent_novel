from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from agents.novel import NovelAgent
from agents.persistence.graph_tables import (
    ensure_graph_tables,
    load_character_entities,
    persist_chapter_artifacts,
    replace_timeline_next_edges_from_state,
    validate_timeline_event_id,
)
from agents.persistence.storage import load_chapter, load_state, save_state, list_chapters
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
)
from webapp.backend.schemas import CreateNovelRequest, RunModeRequest
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
        st_now = apply_chapter_event_selection(st_now, int(chapter_index), req)
        save_state(novel_id, st_now)
        ensure_graph_tables(novel_id)
        replace_timeline_next_edges_from_state(novel_id, st_now)


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
    """人物实体表 `character_entities.json`：供前端主视角/配角等多选候选项。"""
    if not load_state(novel_id):
        raise HTTPException(status_code=404, detail="novel not found")
    ensure_graph_tables(novel_id)
    rows = load_character_entities(novel_id)
    ids = [
        str(r.get("character_id") or "").strip()
        for r in rows
        if str(r.get("character_id") or "").strip()
    ]
    return {"novel_id": novel_id, "characters": rows, "character_ids": ids}


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
    manual_time_slot = bool((req.time_slot_override or "").strip())
    pov_ids = list(req.pov_character_ids_override or [])
    if (not pov_ids) and req.pov_character_id_override:
        pov_ids = [req.pov_character_id_override]
    llm_user_task = build_llm_user_task(novel_id, req.user_task, req, inferred, pov_ids)
    st0 = load_state(novel_id)
    pre_chapter_index = req.chapter_index or ((st0.meta.current_chapter_index + 1) if st0 else 1)
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
            timeline_event_focus_id=req_timeline_focus_id(req),
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
    state_obj = load_state(novel_id)
    resp["state"] = state_obj.model_dump(mode="json") if state_obj else None
    return resp


@router.post("/{novel_id}/preview_input")
def preview_mode_input(novel_id: str, req: RunModeRequest) -> Dict[str, Any]:
    inferred = infer_time_slot(novel_id, req)
    manual_time_slot = bool((req.time_slot_override or "").strip())
    pov_ids = list(req.pov_character_ids_override or [])
    if (not pov_ids) and req.pov_character_id_override:
        pov_ids = [req.pov_character_id_override]
    llm_user_task = build_llm_user_task(novel_id, req.user_task, req, inferred, pov_ids)
    try:
        return agent.preview_input(
            novel_id=novel_id,
            mode=req.mode,
            user_task=llm_user_task,
            chapter_index=req.chapter_index,
            time_slot_override=inferred,
            manual_time_slot=manual_time_slot,
            pov_character_ids_override=pov_ids,
            supporting_character_ids=(req.supporting_character_ids or []),
            lore_tags=req.lore_tags,
            timeline_event_focus_id=req_timeline_focus_id(req),
        )
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
        manual_time_slot = bool((req.time_slot_override or "").strip())
        pov_ids = list(req.pov_character_ids_override or [])
        if (not pov_ids) and req.pov_character_id_override:
            pov_ids = [req.pov_character_id_override]
        llm_user_task = build_llm_user_task(novel_id, req.user_task, req, inferred, pov_ids)
        llm_opts = llm_call_options(req)

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
                    timeline_event_focus_id=req_timeline_focus_id(req),
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
                plan.next_state = apply_chapter_event_selection(plan.next_state, chapter_index, req)

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
                    timeline_event_focus_id=req_timeline_focus_id(req),
                    write_mode=write_mode,
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
                    timeline_event_id=validate_timeline_event_id(next_state, req_timeline_focus_id(req)),
                    time_slot=plan.time_slot,
                    pov_character_id=plan.pov_character_id,
                    who_is_present=plan.who_is_present,
                    beats=plan.beats,
                    content=content_text,
                    usage_metadata=usage_meta,
                )
                persist_chapter_artifacts(
                    novel_id=novel_id,
                    chapter=record,
                    next_state=next_state,
                    chapter_preset_name=req.chapter_preset_name,
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
                        timeline_event_focus_id=req_timeline_focus_id(req),
                    )
                    yield sse_pack("phase", {"name": "next_status_done", "has_text": bool((next_status or "").strip())})
                except Exception as e:
                    logger.warning("Failed to generate next_status (stream): %s", e)
                    yield sse_pack("phase", {"name": "next_status_failed", "error": str(e)})

                yield sse_pack(
                    "done",
                    {
                        "novel_id": novel_id,
                        "mode": req.mode,
                        "chapter_index": chapter_index,
                        "state_updated": True,
                        "usage_metadata": usage_meta,
                        "plan": plan.model_dump(mode="json"),
                        "state": (load_state(novel_id).model_dump(mode="json") if load_state(novel_id) else None),
                        "next_status": next_status or None,
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
                    timeline_event_focus_id=req_timeline_focus_id(req),
                )
                _sync_after_run_if_event(novel_id, req, result.chapter_index)
                state_obj = load_state(novel_id)
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
