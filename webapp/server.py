from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agents.persistence.graph_tables import (
    ensure_graph_tables,
    load_character_relations,
    load_event_relations,
    remap_timeline_numeric_edges_after_delete,
    timeline_next_graph_neighbors,
    persist_chapter_artifacts,
    resolve_chapter_event_ids,
    replace_appear_edges_for_chapter,
    replace_timeline_next_edges_from_state,
    save_character_entities,
    save_character_relations,
    save_event_rows,
    save_event_relations,
    sync_chapter_table_from_record,
    sync_timeline_event_entity_rows,
    update_chapter_table,
)
from agents.novel import NovelAgent
from agents.lore.lore_summary import get_lore_summary, load_cached_summary, source_hash_from_map
from agents.persistence.storage import load_state, save_state, load_chapter, save_chapter, get_chapters_dir, list_chapters
from agents.state.state_models import CharacterState, ChapterPlan, ChapterRecord, NovelState, TimelineEvent
from webapp.frontend_assets import run_frontend_startup
from webapp.schemas import BuildLoreSummaryRequest, CreateNovelRequest, RunModeRequest

from pydantic import BaseModel


app = FastAPI(title="AI Novel Agent")

# 后端日志：用于定位 Web/接口/异常问题
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("webapp.server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="webapp/templates")
app.mount("/static", StaticFiles(directory="webapp/static"), name="static")

agent = NovelAgent()

# ---- 自动构建前端（可选）----
# 当你改了 Vue 源码但忘了手动 npm run build 时，这里会在 FastAPI 启动时自动检测并构建。
_vite_frontend_dir = Path("webapp/frontend")
_vite_dist_dir = _vite_frontend_dir / "dist"


@app.on_event("startup")
def _maybe_build_frontend():
    run_frontend_startup(app, logger, _vite_frontend_dir, _vite_dist_dir)


@app.middleware("http")
async def log_http_requests(request: Request, call_next):
    query = request.url.query
    logger.info("REQ %s %s%s", request.method, request.url.path, (("?" + query) if query else ""))
    try:
        response = await call_next(request)
        logger.info("RES %s %s -> %s", request.method, request.url.path, response.status_code)
        return response
    except Exception:
        logger.exception("ERR %s %s", request.method, request.url.path)
        raise


def _resolve_anchor_time_slot(novel_id: str, anchor_id: Optional[str]) -> Optional[str]:
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


def _infer_time_slot(novel_id: str, req: RunModeRequest) -> Optional[str]:
    """
    time_slot 推导优先级：
      1) time_slot_override（手动）
      2) 区间语义 after/before -> 组合提示
      3) deprecated 的 insert_anchor_id -> 单锚点 time_slot
      4) None（交给 agent 自行延续/推断）
    """
    if req.time_slot_override and str(req.time_slot_override).strip():
        return req.time_slot_override

    existing_slot = _resolve_anchor_time_slot(novel_id, req.existing_event_id)
    if existing_slot:
        return existing_slot

    if req.new_event_time_slot and str(req.new_event_time_slot).strip():
        return str(req.new_event_time_slot).strip()

    after_slot = _resolve_anchor_time_slot(novel_id, req.insert_after_id)
    before_slot = _resolve_anchor_time_slot(novel_id, req.insert_before_id)
    if after_slot and before_slot:
        return f"{after_slot}之后~{before_slot}之前"
    if after_slot:
        return f"{after_slot}之后"
    if before_slot:
        return f"{before_slot}之前"

    legacy_slot = _resolve_anchor_time_slot(novel_id, req.insert_anchor_id)
    return legacy_slot


def _llm_call_options(req: RunModeRequest) -> Optional[Dict[str, Any]]:
    """将前端可选 LLM 参数转为 agent 使用的 bind 字典；全空则走服务端默认。"""
    opts: Dict[str, Any] = {}
    if req.llm_temperature is not None:
        opts["temperature"] = float(req.llm_temperature)
    if req.llm_top_p is not None:
        opts["top_p"] = float(req.llm_top_p)
    if req.llm_max_tokens is not None:
        opts["max_tokens"] = int(req.llm_max_tokens)
    return opts or None


def _timeline_idx(node_id: Optional[str]) -> Optional[int]:
    raw = str(node_id or "").strip()
    if not raw.startswith("ev:timeline:"):
        return None
    try:
        return int(raw.split("ev:timeline:", 1)[1].strip())
    except Exception:
        return None


def _apply_chapter_event_selection(next_state: NovelState, chapter_index: int, req: RunModeRequest) -> NovelState:
    """
    新时序语义：
    - existing_event_id: 把本章绑定到已有事件
    - new_event_*: 新建事件并插入前后位置后绑定本章
    """
    tl = list(next_state.world.timeline or [])

    # 清理旧绑定，避免同一章重复归属
    for ev in tl:
        if ev.chapter_index == chapter_index:
            ev.chapter_index = None

    existing_idx = _timeline_idx(req.existing_event_id)
    if existing_idx is not None and 0 <= existing_idx < len(tl):
        tl[existing_idx].chapter_index = chapter_index
        next_state.world.timeline = tl
        return next_state

    new_slot = str(req.new_event_time_slot or "").strip()
    new_summary = str(req.new_event_summary or "").strip()
    if not (new_slot and new_summary):
        next_state.world.timeline = tl
        return next_state

    prev_idx = _timeline_idx(req.new_event_prev_id)
    next_idx = _timeline_idx(req.new_event_next_id)
    insert_at = len(tl)
    if prev_idx is not None and 0 <= prev_idx < len(tl):
        insert_at = prev_idx + 1
    elif next_idx is not None and 0 <= next_idx < len(tl):
        insert_at = next_idx
    if next_idx is not None and 0 <= next_idx < len(tl):
        insert_at = min(insert_at, next_idx)
    insert_at = max(0, min(insert_at, len(tl)))

    from agents.state.state_models import TimelineEvent

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


def _build_llm_user_task(
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
        idx = _timeline_idx(event_id)
        if idx is None or not (0 <= idx < len(timeline)):
            return event_id
        ev = timeline[idx]
        return f"{event_id}（{ev.time_slot}｜{ev.summary}）"

    existing_id = str(req.existing_event_id or "").strip()
    if existing_id.startswith("ev:timeline:") and st:
        idx = _timeline_idx(existing_id)
        if idx is not None and 0 <= idx < len(timeline):
            ev = timeline[idx]
            lines.append(f"章节归属时间线：{existing_id}（{ev.time_slot}｜{ev.summary}）")
            preds, succs = timeline_next_graph_neighbors(novel_id, existing_id)
            if preds or succs:
                for pid in preds:
                    pi = _timeline_idx(pid)
                    if pi is not None and 0 <= pi < len(timeline):
                        pev = timeline[pi]
                        lines.append(
                            f"关系图前置事件（timeline_next）：{pid}（{pev.time_slot}｜{pev.summary}）"
                        )
                for sid in succs:
                    si = _timeline_idx(sid)
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


def _req_timeline_focus_id(req: RunModeRequest) -> Optional[str]:
    x = (req.existing_event_id or "").strip()
    return x if x.startswith("ev:timeline:") else None


def _prebuild_chapter_graph_records(
    novel_id: str,
    req: RunModeRequest,
    chapter_index: int,
    inferred_time_slot: Optional[str],
    pov_ids: List[str],
) -> None:
    """
    生成前预构建三表中的“本章骨架”：
    - storage/novels/{id}/chapter_tables/{chapter}.json：章节表骨架（勿写入正文 chapters/）
    - graph/event_relations.json：先落主要人物 -> 本章 的 appear 边
    - 若已选择章节归属事件（已有/新建），先把 chapter_index 绑定到 timeline 事件
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
        st = _apply_chapter_event_selection(st, chapter_index, req)
        save_state(novel_id, st)
        replace_timeline_next_edges_from_state(novel_id, st)

    major_chars = [str(x).strip() for x in (pov_ids or []) if str(x).strip()]
    major_chars.extend([str(x).strip() for x in (req.supporting_character_ids or []) if str(x).strip()])
    if not major_chars and st.continuity.pov_character_id:
        major_chars.append(str(st.continuity.pov_character_id).strip())
    major_chars = [x for i, x in enumerate(major_chars) if x and x not in major_chars[:i]]

    # 1) 预构建人物实体表（按当前 state 角色 + 本次主要角色占位）
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

    # 2) 预构建事件实体表（按当前 state.timeline）
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

    chapter_time_slot = str(inferred_time_slot or st.continuity.time_slot or "未设置").strip() or "未设置"
    event_ids = resolve_chapter_event_ids(st, chapter_index, chapter_time_slot)
    update_chapter_table(
        novel_id=novel_id,
        chapter_index=chapter_index,
        time_slot=chapter_time_slot,
        character_ids=[f"char:{c}" for c in major_chars],
        event_ids=event_ids,
    )

    # 预构建“主要人物 -> 本章” appear 边（标签可被后续真实章节出场信息覆盖）
    rows = load_event_relations(novel_id)
    target = f"ev:chapter:{chapter_index}"
    rows = [
        r for r in rows
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


@app.get("/", response_class=HTMLResponse)
def index():
    # 优先返回 Vite 前端 dist；否则回退到旧模板页
    vite_index = _vite_dist_dir / "index.html"
    if vite_index.exists():
        return FileResponse(str(vite_index), media_type="text/html")
    return FileResponse("webapp/templates/index.html", media_type="text/html")


@app.post("/api/novels")
def create_novel(req: CreateNovelRequest):
    novel_id = str(uuid4())
    agent.create_novel_stub(
        novel_id=novel_id,
        novel_title=req.novel_title,
        start_time_slot=req.start_time_slot,
        pov_character_id=req.pov_character_id,
        lore_tags=req.lore_tags,
    )

    # 如果用户在创建时就给了 initial_user_task，也可以直接初始化 state
    if req.initial_user_task and req.initial_user_task.strip():
        try:
            agent.init_state(
                novel_id=novel_id,
                user_task=req.initial_user_task,
                lore_tags=req.lore_tags,
            )
        except Exception:
            # 初始化失败不阻止创建，前端可再点 init_state
            pass

    return {"novel_id": novel_id}


@app.post("/api/lore/summary/build")
def build_lore_summary_api(req: BuildLoreSummaryRequest):
    tags = [str(t).strip() for t in (req.tags or []) if str(t).strip()]
    if not tags:
        raise HTTPException(status_code=400, detail="tags is required")
    data = agent.build_lore_summary_llm(tags, force=bool(req.force))
    return {
        "summary_id": data.get("summary_id"),
        "tags": data.get("tags"),
        "mode": data.get("mode"),
        "cached": bool(data.get("cached")),
        "summary_text": data.get("summary_text"),
        "tag_summaries": data.get("tag_summaries") or [],
    }


@app.get("/api/lore/summary/{summary_id}")
def get_lore_summary_api(summary_id: str):
    data = get_lore_summary(summary_id)
    if not data:
        raise HTTPException(status_code=404, detail="summary not found")
    return {
        "summary_id": data.get("summary_id"),
        "tags": data.get("tags"),
        "summary_text": data.get("summary_text"),
        "tag_summaries": data.get("tag_summaries") or [],
    }


@app.post("/api/novels/{novel_id}/run")
def run_mode(novel_id: str, req: RunModeRequest) -> Dict[str, Any]:
    inferred_time_slot = _infer_time_slot(novel_id, req)
    manual_time_slot = bool((req.time_slot_override or "").strip())
    pov_ids = (req.pov_character_ids_override or [])
    if (not pov_ids) and req.pov_character_id_override:
        pov_ids = [req.pov_character_id_override]
    llm_user_task = _build_llm_user_task(novel_id, req.user_task, req, inferred_time_slot, pov_ids)
    st0 = load_state(novel_id)
    pre_chapter_index = req.chapter_index or ((st0.meta.current_chapter_index + 1) if st0 else 1)
    if req.mode in {"plan_only", "write_chapter", "revise_chapter"}:
        try:
            _prebuild_chapter_graph_records(
                novel_id=novel_id,
                req=req,
                chapter_index=int(pre_chapter_index),
                inferred_time_slot=inferred_time_slot,
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
            time_slot_override=inferred_time_slot,
            manual_time_slot=manual_time_slot,
            pov_character_ids_override=pov_ids,
            supporting_character_ids=(req.supporting_character_ids or []),
            lore_tags=req.lore_tags,
            llm_options=_llm_call_options(req),
            timeline_event_focus_id=_req_timeline_focus_id(req),
        )
    except Exception as e:
        logger.exception("run_mode failed novel_id=%s mode=%s", novel_id, req.mode)
        raise HTTPException(status_code=400, detail=str(e))

    if req.mode in {"plan_only", "write_chapter", "revise_chapter"} and result.chapter_index is not None:
        has_event_selection = bool(
            (req.existing_event_id or "").strip()
            or ((req.new_event_time_slot or "").strip() and (req.new_event_summary or "").strip())
        )
        if has_event_selection:
            st_now = load_state(novel_id)
            ch_now = load_chapter(novel_id, int(result.chapter_index))
            if st_now and ch_now:
                st_now = _apply_chapter_event_selection(st_now, int(result.chapter_index), req)
                save_state(novel_id, st_now)
                ensure_graph_tables(novel_id)
                replace_timeline_next_edges_from_state(novel_id, st_now)
                sync_chapter_table_from_record(novel_id, ch_now, state=st_now)

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


@app.post("/api/novels/{novel_id}/preview_input")
def preview_mode_input(novel_id: str, req: RunModeRequest) -> Dict[str, Any]:
    inferred_time_slot = _infer_time_slot(novel_id, req)
    manual_time_slot = bool((req.time_slot_override or "").strip())
    pov_ids = (req.pov_character_ids_override or [])
    if (not pov_ids) and req.pov_character_id_override:
        pov_ids = [req.pov_character_id_override]
    llm_user_task = _build_llm_user_task(novel_id, req.user_task, req, inferred_time_slot, pov_ids)
    try:
        return agent.preview_input(
            novel_id=novel_id,
            mode=req.mode,
            user_task=llm_user_task,
            chapter_index=req.chapter_index,
            time_slot_override=inferred_time_slot,
            manual_time_slot=manual_time_slot,
            pov_character_ids_override=pov_ids,
            supporting_character_ids=(req.supporting_character_ids or []),
            lore_tags=req.lore_tags,
            timeline_event_focus_id=_req_timeline_focus_id(req),
        )
    except Exception as e:
        logger.exception("preview_input failed novel_id=%s mode=%s", novel_id, req.mode)
        raise HTTPException(status_code=400, detail=str(e))


def _sse_pack(event: str, data: Any) -> bytes:
    # SSE: "event: xxx\ndata: <json>\n\n"
    import json as _json

    payload = _json.dumps({"event": event, "data": data}, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


@app.post("/api/novels/{novel_id}/run_stream")
def run_mode_stream(novel_id: str, req: RunModeRequest, request: Request):
    """
    流式运行：通过 SSE 持续推送阶段进度与正文片段。
    前端可实时显示，不用干等。
    """

    async def gen():
        async def _disconnected() -> bool:
            try:
                return await request.is_disconnected()
            except Exception:
                return False

        yield _sse_pack("start", {"novel_id": novel_id, "mode": req.mode})

        inferred_time_slot = _infer_time_slot(novel_id, req)
        manual_time_slot = bool((req.time_slot_override or "").strip())
        pov_ids = (req.pov_character_ids_override or [])
        if (not pov_ids) and req.pov_character_id_override:
            pov_ids = [req.pov_character_id_override]
        llm_user_task = _build_llm_user_task(novel_id, req.user_task, req, inferred_time_slot, pov_ids)
        llm_opts = _llm_call_options(req)

        try:
            # 这里对 write_chapter 做“正文流式”，其它模式走一次性结果但也会发阶段事件。
            if req.mode in {"write_chapter", "revise_chapter"}:
                if await _disconnected():
                    logger.info("run_stream client disconnected early. novel_id=%s mode=%s", novel_id, req.mode)
                    return
                yield _sse_pack("phase", {"name": "planning"})
                # 让 agent.run() 自己处理自动 init_state；我们这里需要拿到 plan 才能流式写正文
                # 因此：先调用 agent.run(mode=plan_only) 得到 plan+state，再流式写，然后手动落盘逻辑由 agent.run 做。
                # 但为了复用现有落盘，我们改成：直接复用 agent.plan_chapter + agent.write_chapter_text_stream + 手动保存，与 agent.run 保持一致。
                from agents.persistence.storage import load_state
                from agents.state.state_models import ChapterRecord

                st = load_state(novel_id)
                if not st:
                    raise ValueError("novel not found")
                if not st.meta.initialized:
                    raise ValueError("state not initialized. please run init_state first")

                chapter_index = req.chapter_index or (st.meta.current_chapter_index + 1)
                try:
                    _prebuild_chapter_graph_records(
                        novel_id=novel_id,
                        req=req,
                        chapter_index=int(chapter_index),
                        inferred_time_slot=inferred_time_slot,
                        pov_ids=pov_ids,
                    )
                except Exception as e:
                    logger.warning("prebuild chapter graph records failed(stream): %s", e)
                plan_json: Optional[Dict[str, Any]] = None
                for item in agent.plan_chapter_stream(
                    novel_id=novel_id,
                    user_task=llm_user_task,
                    chapter_index=chapter_index,
                    time_slot_override=inferred_time_slot,
                    pov_character_ids_override=pov_ids,
                    supporting_character_ids=(req.supporting_character_ids or []),
                    minimal_state_for_prompt=manual_time_slot,
                    lore_tags=req.lore_tags,
                    llm_options=llm_opts,
                    timeline_event_focus_id=_req_timeline_focus_id(req),
                ):
                    if await _disconnected():
                        logger.info("run_stream disconnected during plan stream. novel_id=%s chapter=%s", novel_id, chapter_index)
                        return
                    txt = str(item.get("delta", "") or "")
                    if txt:
                        yield _sse_pack("plan_content", {"delta": txt})
                    if item.get("done"):
                        plan_json = item.get("plan") or {}
                if not plan_json:
                    raise ValueError("plan stream failed: empty plan")
                plan = ChapterPlan.model_validate(plan_json)
                # 允许 next_state 是补丁：合并成完整状态再落盘
                try:
                    plan.next_state = NovelAgent.merge_state(st, plan.next_state)  # type: ignore
                except Exception as e:
                    logger.warning("merge_state failed in stream save: %s", e)
                plan.next_state = _apply_chapter_event_selection(plan.next_state, chapter_index, req)

                yield _sse_pack("phase", {"name": "writing", "chapter_index": chapter_index})
                parts: List[str] = []
                usage_meta: Dict[str, Any] = {}
                for item in agent.write_chapter_text_stream(
                    novel_id=novel_id,
                    plan=plan,
                    user_task=llm_user_task,
                    minimal_state_for_prompt=manual_time_slot,
                    lore_tags=req.lore_tags,
                    time_slot_hint=inferred_time_slot,
                    pov_character_ids_override=pov_ids,
                    supporting_character_ids=(req.supporting_character_ids or []),
                    llm_options=llm_opts,
                    timeline_event_focus_id=_req_timeline_focus_id(req),
                ):
                    if await _disconnected():
                        logger.info("run_stream disconnected during write stream. novel_id=%s chapter=%s", novel_id, chapter_index)
                        return
                    txt = str(item.get("delta", "") or "")
                    if txt:
                        parts.append(txt)
                        yield _sse_pack("content", {"delta": txt})
                    um = item.get("usage_metadata") or {}
                    if isinstance(um, dict) and um:
                        usage_meta = um

                content_text = "".join(parts).strip()

                if await _disconnected():
                    logger.info("run_stream disconnected before saving. novel_id=%s chapter=%s", novel_id, chapter_index)
                    return
                yield _sse_pack("phase", {"name": "saving"})
                record = ChapterRecord(
                    chapter_index=chapter_index,
                    chapter_preset_name=req.chapter_preset_name,
                    time_slot=plan.time_slot,
                    pov_character_id=plan.pov_character_id,
                    who_is_present=plan.who_is_present,
                    beats=plan.beats,
                    content=content_text,
                    usage_metadata=usage_meta,
                )
                next_state = plan.next_state
                persist_chapter_artifacts(
                    novel_id=novel_id,
                    chapter=record,
                    next_state=next_state,
                    chapter_preset_name=req.chapter_preset_name,
                )

                # 同步写出纯文本到 outputs/（保持脚本版的落盘习惯）
                try:
                    from agents.text_utils import write_outputs_txt

                    title = (st.meta.novel_title or "未命名小说") if st else "未命名小说"
                    out_path = write_outputs_txt(title, chapter_index, content_text)
                    yield _sse_pack("phase", {"name": "outputs_written", "path": out_path})
                except Exception as e:
                    logger.warning("Failed to write outputs txt (stream): %s", e)
                    yield _sse_pack(
                        "phase",
                        {"name": "outputs_write_failed", "error": str(e)},
                    )

                next_status = ""
                try:
                    if await _disconnected():
                        logger.info("run_stream disconnected before next_status. novel_id=%s chapter=%s", novel_id, chapter_index)
                        return
                    yield _sse_pack("phase", {"name": "next_status"})
                    next_status = agent.suggest_next_status(
                        novel_id=novel_id,
                        user_task=llm_user_task,
                        chapter_index=chapter_index,
                        latest_content=content_text,
                        llm_options=llm_opts,
                        timeline_event_focus_id=_req_timeline_focus_id(req),
                    )
                    yield _sse_pack("phase", {"name": "next_status_done", "has_text": bool((next_status or "").strip())})
                except Exception as e:
                    logger.warning("Failed to generate next_status (stream): %s", e)
                    yield _sse_pack("phase", {"name": "next_status_failed", "error": str(e)})

                yield _sse_pack(
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
            else:
                if await _disconnected():
                    logger.info("run_stream disconnected before non-stream run. novel_id=%s mode=%s", novel_id, req.mode)
                    return
                yield _sse_pack("phase", {"name": "running"})
                stx = load_state(novel_id)
                chapter_index = req.chapter_index or ((stx.meta.current_chapter_index + 1) if stx else 1)
                try:
                    _prebuild_chapter_graph_records(
                        novel_id=novel_id,
                        req=req,
                        chapter_index=int(chapter_index),
                        inferred_time_slot=inferred_time_slot,
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
                    time_slot_override=inferred_time_slot,
                    manual_time_slot=manual_time_slot,
                    pov_character_ids_override=pov_ids,
                    supporting_character_ids=(req.supporting_character_ids or []),
                    lore_tags=req.lore_tags,
                    llm_options=llm_opts,
                    timeline_event_focus_id=_req_timeline_focus_id(req),
                )
                if req.mode in {"plan_only", "write_chapter", "revise_chapter"} and result.chapter_index is not None:
                    has_event_selection = bool(
                        (req.existing_event_id or "").strip()
                        or ((req.new_event_time_slot or "").strip() and (req.new_event_summary or "").strip())
                    )
                    if has_event_selection:
                        st_now = load_state(novel_id)
                        ch_now = load_chapter(novel_id, int(result.chapter_index))
                        if st_now and ch_now:
                            st_now = _apply_chapter_event_selection(st_now, int(result.chapter_index), req)
                            save_state(novel_id, st_now)
                            ensure_graph_tables(novel_id)
                            replace_timeline_next_edges_from_state(novel_id, st_now)
                            sync_chapter_table_from_record(novel_id, ch_now, state=st_now)
                state_obj = load_state(novel_id)
                yield _sse_pack(
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
                yield _sse_pack("error", {"message": str(e)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # 关闭反向代理缓冲（如果有的话）
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/novels/{novel_id}/state")
def get_state(novel_id: str):
    state = load_state(novel_id)
    if not state:
        raise HTTPException(status_code=404, detail="novel not found")
    return state.model_dump(mode="json")


@app.get("/api/novels/{novel_id}/chapters/{chapter_index}")
def get_chapter(novel_id: str, chapter_index: int):
    chapter = load_chapter(novel_id, chapter_index)
    if not chapter:
        raise HTTPException(status_code=404, detail="chapter not found")
    return chapter.model_dump(mode="json")


@app.get("/api/novels/{novel_id}/anchors")
def list_event_anchors(novel_id: str):
    """
    返回“事件网插入锚点”下拉选项。
    - 时间线事件：ev:timeline:{idx}
    - 章节事件：ev:chapter:{chapter_index}
    """
    state = load_state(novel_id)
    if not state:
        raise HTTPException(status_code=404, detail="novel not found")

    anchors: List[Dict[str, Any]] = []
    # timeline anchors
    for idx, ev in enumerate(state.world.timeline or []):
        anchors.append(
            {
                "id": f"ev:timeline:{idx}",
                "type": "timeline_event",
                "label": f"{ev.time_slot}：{ev.summary}",
                "time_slot": ev.time_slot,
            }
        )

    # chapter anchors
    for chap in list_chapters(novel_id):
        anchors.append(
            {
                "id": f"ev:chapter:{chap.chapter_index}",
                "type": "chapter_event",
                "label": f"章节事件 · {chap.time_slot}",
                "time_slot": chap.time_slot,
            }
        )

    # 让“较新的”在前面：先按 time_slot 字符串逆序（不保证严格时序，但对可读性够用）
    anchors.sort(key=lambda x: (x.get("time_slot") or ""), reverse=True)
    return {"novel_id": novel_id, "anchors": anchors, "count": len(anchors)}


@app.get("/api/novels/{novel_id}/graph")
def get_novel_graph(novel_id: str, view: str = "mixed"):
    """
    返回可视化图谱数据（nodes/edges）。
    view:
      - people: 人物关系网
      - events: 剧情事件网（以时间线/章节事件为中心）
      - mixed: 混合网
    """
    state = load_state(novel_id)
    if not state:
        raise HTTPException(status_code=404, detail="novel not found")

    view = (view or "mixed").lower()
    if view not in {"people", "events", "mixed"}:
        raise HTTPException(status_code=400, detail="view must be one of: people, events, mixed")

    ensure_graph_tables(novel_id)
    char_relations = load_character_relations(novel_id)
    event_relations = load_event_relations(novel_id)

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    node_ids: set[str] = set()

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

    # ---- 人物节点 + 人物关系边 ----
    # 约定：events 视图是“纯事件网”，不混入人物节点（否则会看起来像混合网）
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

    # ---- 事件节点（时间线 + 章节）----
    if view in {"events", "mixed"}:
        # timeline events from state
        for idx, ev in enumerate(state.world.timeline or []):
            eid = f"ev:timeline:{idx}"
            label = f"{ev.time_slot}：{ev.summary}"
            add_node(eid, label, "timeline_event", {"data": ev.model_dump(mode="json")})

        # timeline_next / appear 来自事件关系表
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

        # chapter events: from saved chapters
        for chap in list_chapters(novel_id):
            cid = f"ev:chapter:{chap.chapter_index}"
            label = f"章节事件 · {chap.time_slot}"
            add_node(cid, label, "chapter_event", {"data": chap.model_dump(mode="json")})

            # chapter_belongs：按 timeline.chapter_index / time_slot 匹配
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

    # ---- 势力节点（world.factions） ----
    if view == "mixed":
        for fname, fdesc in (state.world.factions or {}).items():
            fid = f"fac:{fname}"
            add_node(fid, fname, "faction", {"data": {"description": fdesc}})

    return {"view": view, "nodes": nodes, "edges": edges}


class GraphNodePatchRequest(BaseModel):
    node_id: str
    patch: Dict[str, Any]


@app.patch("/api/novels/{novel_id}/graph/node")
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


class GraphNodeCreateRequest(BaseModel):
    node_type: str  # character | timeline_event | faction
    character_id: Optional[str] = None
    description: Optional[str] = None
    current_location: Optional[str] = None
    time_slot: Optional[str] = None
    summary: Optional[str] = None
    faction_name: Optional[str] = None
    chapter_index: Optional[int] = None


@app.post("/api/novels/{novel_id}/graph/nodes")
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


@app.delete("/api/novels/{novel_id}/graph/nodes")
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


class GraphRelationshipRequest(BaseModel):
    source: str
    target: str
    label: str = ""
    op: str = "set"  # set | delete


@app.post("/api/novels/{novel_id}/graph/relationship")
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
        r for r in rows
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


class TimelineNeighborsRequest(BaseModel):
    node_id: str
    prev_source: Optional[str] = None   # ev:timeline:* or ""
    next_target: Optional[str] = None   # ev:timeline:* or ""


@app.patch("/api/novels/{novel_id}/graph/timeline-neighbors")
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
        r for r in rows
        if not (
            str(r.get("kind", "")).strip().lower() == "timeline_next"
            and (str(r.get("source", "")).strip() == node_id or str(r.get("target", "")).strip() == node_id)
        )
    ]
    if prev_source:
        rows.append({"source": prev_source, "target": node_id, "label": "时间推进", "kind": "timeline_next"})
    # 无下一跳时不写入 target 为空的行：get_graph 会把空 target 画成 draft 占位节点
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


class GraphEdgePatchRequest(BaseModel):
    edge_type: str  # relationship | appear | timeline_next | chapter_belongs
    source: str
    target: str
    new_source: Optional[str] = None
    new_target: Optional[str] = None
    label: Optional[str] = None
    op: str = "set"  # set | delete


@app.patch("/api/novels/{novel_id}/graph/edge")
def patch_graph_edge(novel_id: str, req: GraphEdgePatchRequest):
    """
    图谱边编辑（基于五表真源：人物/事件实体与关系表 + 章节表；章节归属还写 state.timeline）。
    - relationship: 人物关系表
    - appear: 事件关系表（char -> ev:chapter）
    - timeline_next: 事件关系表（ev:timeline -> ev:timeline 或空 target）
    - chapter_belongs: 章节归属事件（ev:chapter -> ev:timeline 或空表示取消）
    """
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
        if not (src.startswith("char:") and tgt.startswith("char:") and nsrc.startswith("char:") and ntgt.startswith("char:")):
            raise HTTPException(status_code=400, detail="relationship requires char:* -> char:*")
        rows = load_character_relations(novel_id)
        rows = [
            r for r in rows
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
            r for r in rows
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

        # 解绑：清理所有 timeline 事件上对该章的绑定
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
        chap = load_chapter(novel_id, chap_idx)
        if chap:
            sync_chapter_table_from_record(novel_id, chap, state=state)
        return {"ok": True}

    raise HTTPException(status_code=400, detail="unsupported edge_type")


@app.get("/api/novels")
def list_novels():
    """
    返回已有小说列表，用于前端下拉选择。
    novel_id 保持内部 uuid；novel_title 用于展示（没有则回退到 novel_id/未命名）。
    """
    base = Path("storage") / "novels"
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
            # 读取异常不影响其它小说列表
            continue

    # 按更新时间倒序，最新在前
    novels.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return {"novels": novels}


@app.get("/api/lore/tags")
def get_lore_tags():
    tags = agent.lore_loader.get_lore_tags()
    groups = agent.lore_loader.get_lore_tag_groups()
    return {"tags": tags, "groups": groups, "count": len(tags)}


@app.get("/api/lore/preview")
def get_lore_preview(tag: str, max_chars: int = 0, compact: bool = False):
    logger.info("preview tag=%s max_chars=%s compact=%s", tag, max_chars, compact)
    if compact:
        # compact 视为“摘要预览”：读取单 tag 的 LLM 摘要缓存（llm_tag_v1）
        md = agent.lore_loader.get_markdown_by_tag(tag=tag) or ""
        tag_src_hash = source_hash_from_map({tag: md})
        hit = load_cached_summary([tag], tag_src_hash, mode="llm_tag_v1")
        preview = ""
        if hit:
            rows = hit.get("tag_summaries") or []
            if isinstance(rows, list) and rows:
                first = rows[0] if isinstance(rows[0], dict) else {}
                preview = str(first.get("summary", "")).strip()
        if not preview:
            preview = "该标签暂无摘要缓存，请先点击“生成当前Tag摘要”。"
        if max_chars and max_chars > 0 and len(preview) > max_chars:
            preview = preview[:max_chars]
    else:
        preview = agent.lore_loader.get_preview_by_tag(tag=tag, max_chars=max_chars)
    return {"tag": tag, "preview": preview}

