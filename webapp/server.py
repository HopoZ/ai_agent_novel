from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agents.novel_agent import NovelAgent
from agents.lore_summary import get_lore_summary, load_cached_summary, source_hash_from_map
from agents.storage import load_state, load_chapter, get_chapters_dir, list_chapters
from agents.state_models import NovelState, ChapterRecord
from webapp.frontend_assets import run_frontend_startup
from webapp.schemas import BuildLoreSummaryRequest, CreateNovelRequest, RunModeRequest


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

    try:
        result = agent.run(
            novel_id=novel_id,
            mode=req.mode,
            user_task=req.user_task,
            chapter_index=req.chapter_index,
            chapter_preset_name=req.chapter_preset_name,
            time_slot_override=inferred_time_slot,
            manual_time_slot=manual_time_slot,
            pov_character_ids_override=pov_ids,
            supporting_character_ids=(req.supporting_character_ids or []),
            lore_tags=req.lore_tags,
        )
    except Exception as e:
        logger.exception("run_mode failed novel_id=%s mode=%s", novel_id, req.mode)
        raise HTTPException(status_code=400, detail=str(e))

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
    try:
        return agent.preview_input(
            novel_id=novel_id,
            mode=req.mode,
            user_task=req.user_task,
            chapter_index=req.chapter_index,
            time_slot_override=inferred_time_slot,
            manual_time_slot=manual_time_slot,
            pov_character_ids_override=pov_ids,
            supporting_character_ids=(req.supporting_character_ids or []),
            lore_tags=req.lore_tags,
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
def run_mode_stream(novel_id: str, req: RunModeRequest):
    """
    流式运行：通过 SSE 持续推送阶段进度与正文片段。
    前端可实时显示，不用干等。
    """

    def gen():
        yield _sse_pack("start", {"novel_id": novel_id, "mode": req.mode})

        inferred_time_slot = _infer_time_slot(novel_id, req)
        manual_time_slot = bool((req.time_slot_override or "").strip())
        pov_ids = (req.pov_character_ids_override or [])
        if (not pov_ids) and req.pov_character_id_override:
            pov_ids = [req.pov_character_id_override]

        try:
            # 这里对 write_chapter 做“正文流式”，其它模式走一次性结果但也会发阶段事件。
            if req.mode in {"write_chapter", "revise_chapter"}:
                yield _sse_pack("phase", {"name": "planning"})
                # 让 agent.run() 自己处理自动 init_state；我们这里需要拿到 plan 才能流式写正文
                # 因此：先调用 agent.run(mode=plan_only) 得到 plan+state，再流式写，然后手动落盘逻辑由 agent.run 做。
                # 但为了复用现有落盘，我们改成：直接复用 agent.plan_chapter + agent.write_chapter_text_stream + 手动保存，与 agent.run 保持一致。
                from agents.storage import load_state, save_chapter, save_state
                from agents.state_models import ChapterRecord
                from datetime import datetime

                # 确保初始化
                st = load_state(novel_id)
                if st and (not st.meta.initialized) and req.mode in {"write_chapter", "revise_chapter"}:
                    yield _sse_pack("phase", {"name": "auto_init"})
                    _, init_usage = agent.init_state_with_usage(
                        novel_id,
                        user_task=f"（自动初始化）{req.user_task}",
                        lore_tags=req.lore_tags,
                    )
                    if init_usage:
                        yield _sse_pack("phase", {"name": "auto_init", "status": "done", "usage_metadata": init_usage})
                    st = load_state(novel_id)

                if not st:
                    raise ValueError("novel not found")

                chapter_index = req.chapter_index or (st.meta.current_chapter_index + 1)
                plan = agent.plan_chapter(
                    novel_id=novel_id,
                    user_task=req.user_task,
                    chapter_index=chapter_index,
                    time_slot_override=inferred_time_slot,
                    pov_character_ids_override=pov_ids,
                    supporting_character_ids=(req.supporting_character_ids or []),
                    include_chapter_context=(not manual_time_slot),
                    lore_tags=req.lore_tags,
                )
                # 允许 next_state 是补丁：合并成完整状态再落盘
                try:
                    plan.next_state = NovelAgent.merge_state(st, plan.next_state)  # type: ignore
                except Exception as e:
                    logger.warning("merge_state failed in stream save: %s", e)

                yield _sse_pack("phase", {"name": "writing", "chapter_index": chapter_index})
                parts: List[str] = []
                usage_meta: Dict[str, Any] = {}
                for item in agent.write_chapter_text_stream(
                    novel_id=novel_id,
                    plan=plan,
                    user_task=req.user_task,
                    include_chapter_context=(not manual_time_slot),
                    lore_tags=req.lore_tags,
                    time_slot_hint=inferred_time_slot,
                    pov_character_ids_override=pov_ids,
                    supporting_character_ids=(req.supporting_character_ids or []),
                ):
                    txt = str(item.get("delta", "") or "")
                    if txt:
                        parts.append(txt)
                        yield _sse_pack("content", {"delta": txt})
                    um = item.get("usage_metadata") or {}
                    if isinstance(um, dict) and um:
                        usage_meta = um

                content_text = "".join(parts).strip()

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
                save_chapter(novel_id, record, chapter_preset_name=req.chapter_preset_name)

                next_state = plan.next_state
                next_state.meta.current_chapter_index = chapter_index
                next_state.meta.updated_at = datetime.utcnow()
                save_state(novel_id, next_state)

                # 同步写出纯文本到 outputs/（保持脚本版的落盘习惯）
                try:
                    from agents.novel_agent import _write_outputs_txt

                    title = (st.meta.novel_title or "未命名小说") if st else "未命名小说"
                    out_path = _write_outputs_txt(title, chapter_index, content_text)
                    yield _sse_pack("phase", {"name": "outputs_written", "path": out_path})
                except Exception as e:
                    logger.warning("Failed to write outputs txt (stream): %s", e)

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
                    },
                )
            else:
                yield _sse_pack("phase", {"name": "running"})
                result = agent.run(
                    novel_id=novel_id,
                    mode=req.mode,
                    user_task=req.user_task,
                    chapter_index=req.chapter_index,
                    chapter_preset_name=req.chapter_preset_name,
                    time_slot_override=inferred_time_slot,
                    manual_time_slot=manual_time_slot,
                    pov_character_ids_override=pov_ids,
                    supporting_character_ids=(req.supporting_character_ids or []),
                    lore_tags=req.lore_tags,
                )
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

        # relationships: {other_id/name: relation}
        for c in state.characters:
            src = f"char:{c.character_id}"
            for other, rel in (c.relationships or {}).items():
                tgt = f"char:{other}"
                add_node(tgt, other, "character")
                add_edge(src, tgt, rel, "relationship")

    # ---- 事件节点（时间线 + 章节）----
    if view in {"events", "mixed"}:
        # timeline events from state
        for idx, ev in enumerate(state.world.timeline or []):
            eid = f"ev:timeline:{idx}"
            label = f"{ev.time_slot}：{ev.summary}"
            add_node(eid, label, "timeline_event", {"data": ev.model_dump(mode="json")})

        # timeline ordering edges (events-only makes this more meaningful)
        for idx in range(0, max(0, len(state.world.timeline or []) - 1)):
            add_edge(f"ev:timeline:{idx}", f"ev:timeline:{idx+1}", "时间推进", "timeline_next")

        # chapter events: from saved chapters
        for chap in list_chapters(novel_id):
            cid = f"ev:chapter:{chap.chapter_index}"
            label = f"章节事件 · {chap.time_slot}"
            add_node(cid, label, "chapter_event", {"data": chap.model_dump(mode="json")})

            # events 视图：不混入人物节点；mixed 视图才连“人物出场 -> 章节事件”
            if view == "mixed":
                for pres in chap.who_is_present or []:
                    ch_id = f"char:{pres.character_id}"
                    add_node(ch_id, pres.character_id, "character")
                    add_edge(ch_id, cid, pres.role_in_scene or "出场", "appear")

    # ---- 势力节点（world.factions） ----
    if view == "mixed":
        for fname, fdesc in (state.world.factions or {}).items():
            fid = f"fac:{fname}"
            add_node(fid, fname, "faction", {"data": {"description": fdesc}})

    return {"view": view, "nodes": nodes, "edges": edges}


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

