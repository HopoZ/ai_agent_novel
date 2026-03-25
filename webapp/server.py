from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from agents.novel_agent import NovelAgent
from agents.storage import load_state, load_chapter, get_chapters_dir
from agents.state_models import NovelState, ChapterRecord


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


def _frontend_need_rebuild() -> bool:
    # 可通过环境变量跳过构建（例如：你只想用开发版 dist）
    if str(os.getenv("SKIP_FRONTEND_BUILD", "")).lower() in {"1", "true", "yes"}:
        return False

    dist_index = _vite_dist_dir / "index.html"
    if not dist_index.exists():
        return True

    src_dir = _vite_frontend_dir / "src"
    if not src_dir.exists():
        return False

    # 取 src 目录最新 mtime，和 dist/index.html 做比较
    latest_src_mtime = 0.0
    for p in src_dir.rglob("*"):
        if not p.is_file():
            continue
        # 限制类型，避免把 node_modules 等计入（理论上 src 下不会有 node_modules）
        if p.suffix.lower() not in {".ts", ".tsx", ".js", ".jsx", ".vue", ".css", ".scss", ".html", ".json"}:
            continue
        latest_src_mtime = max(latest_src_mtime, p.stat().st_mtime)

    dist_mtime = dist_index.stat().st_mtime
    return latest_src_mtime > dist_mtime


@app.on_event("startup")
def _maybe_build_frontend():
    if _frontend_need_rebuild():
        if not _vite_frontend_dir.exists():
            logger.warning("Frontend dir not found: %s", _vite_frontend_dir)
        else:
            logger.info("Frontend dist is stale, running npm build...")
            try:
                # 注意：这是同步执行，会阻塞启动；但能保证你访问到的是最新前端。
                import subprocess

                subprocess.run(
                    ["npm", "run", "build"],
                    cwd=str(_vite_frontend_dir),
                    check=True,
                )
                logger.info("Frontend build finished.")
            except Exception as e:
                logger.exception("Frontend build failed: %s", e)
    else:
        logger.info("Frontend dist is up-to-date, skip build.")

    _mount_vite_assets_if_needed()


def _mount_vite_assets_if_needed() -> None:
    assets_dir = _vite_dist_dir / "assets"
    if not assets_dir.exists():
        return

    # 避免重复 mount
    for r in app.routes:
        if getattr(r, "path", None) == "/assets":
            return

    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="vite_assets")


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


class CreateNovelRequest(BaseModel):
    novel_title: Optional[str] = None
    start_time_slot: Optional[str] = None
    pov_character_id: Optional[str] = None
    initial_user_task: Optional[str] = None
    lore_tags: Optional[List[str]] = None


class RunModeRequest(BaseModel):
    mode: str = Field(
        description="init_state | plan_only | write_chapter | revise_chapter"
    )
    user_task: str
    # 不建议前端显式指定 chapter_index（现实中会有重排/插入等需求）
    # 保留这个字段仅用于兼容/内部调试；推荐使用 insert_anchor_id 来选择插入到事件网的哪一段
    chapter_index: Optional[int] = None
    insert_anchor_id: Optional[str] = Field(
        default=None,
        description="可选：插入锚点。例如 ev:timeline:3 或 ev:chapter:12；用于推导 time_slot_override",
    )
    time_slot_override: Optional[str] = None
    pov_character_id_override: Optional[str] = None
    lore_tags: Optional[List[str]] = None


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


@app.post("/api/novels/{novel_id}/run")
def run_mode(novel_id: str, req: RunModeRequest) -> Dict[str, Any]:
    # 如果用户没有手填 time_slot_override，但选择了“插入锚点”，则用锚点对应的 time_slot
    # 这样生成的事件会自然落在“事件网”的那一段里（以时间段为主锚）
    inferred_time_slot: Optional[str] = None
    if (not req.time_slot_override) and req.insert_anchor_id:
        anchor = req.insert_anchor_id.strip()
        try:
            if anchor.startswith("ev:timeline:"):
                idx_str = anchor.split("ev:timeline:", 1)[1]
                idx = int(idx_str)
                st = load_state(novel_id)
                if st and st.world.timeline and 0 <= idx < len(st.world.timeline):
                    inferred_time_slot = st.world.timeline[idx].time_slot
            elif anchor.startswith("ev:chapter:"):
                idx_str = anchor.split("ev:chapter:", 1)[1]
                chap_idx = int(idx_str)
                chap = load_chapter(novel_id, chap_idx)
                if chap:
                    inferred_time_slot = chap.time_slot
        except Exception:
            inferred_time_slot = None

    try:
        result = agent.run(
            novel_id=novel_id,
            mode=req.mode,
            user_task=req.user_task,
            chapter_index=req.chapter_index,
            time_slot_override=req.time_slot_override or inferred_time_slot,
            pov_character_id_override=req.pov_character_id_override,
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

        # 推导 time_slot（同 run_mode）
        inferred_time_slot: Optional[str] = None
        if (not req.time_slot_override) and req.insert_anchor_id:
            anchor = req.insert_anchor_id.strip()
            try:
                if anchor.startswith("ev:timeline:"):
                    idx_str = anchor.split("ev:timeline:", 1)[1]
                    idx = int(idx_str)
                    st = load_state(novel_id)
                    if st and st.world.timeline and 0 <= idx < len(st.world.timeline):
                        inferred_time_slot = st.world.timeline[idx].time_slot
                elif anchor.startswith("ev:chapter:"):
                    idx_str = anchor.split("ev:chapter:", 1)[1]
                    chap_idx = int(idx_str)
                    chap = load_chapter(novel_id, chap_idx)
                    if chap:
                        inferred_time_slot = chap.time_slot
            except Exception:
                inferred_time_slot = None

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
                    agent.init_state(novel_id, user_task=f"（自动初始化）{req.user_task}", lore_tags=req.lore_tags)
                    st = load_state(novel_id)

                if not st:
                    raise ValueError("novel not found")

                chapter_index = req.chapter_index or (st.meta.current_chapter_index + 1)
                plan = agent.plan_chapter(
                    novel_id=novel_id,
                    user_task=req.user_task,
                    chapter_index=chapter_index,
                    time_slot_override=req.time_slot_override or inferred_time_slot,
                    pov_character_id_override=req.pov_character_id_override,
                    lore_tags=req.lore_tags,
                )
                # 允许 next_state 是补丁：合并成完整状态再落盘
                try:
                    plan.next_state = NovelAgent.merge_state(st, plan.next_state)  # type: ignore
                except Exception as e:
                    logger.warning("merge_state failed in stream save: %s", e)

                yield _sse_pack("phase", {"name": "writing", "chapter_index": chapter_index})
                parts: List[str] = []
                for txt in agent.write_chapter_text_stream(
                    novel_id=novel_id,
                    plan=plan,
                    user_task=req.user_task,
                    lore_tags=req.lore_tags,
                ):
                    parts.append(txt)
                    yield _sse_pack("content", {"delta": txt})

                content_text = "".join(parts).strip()

                yield _sse_pack("phase", {"name": "saving"})
                record = ChapterRecord(
                    chapter_index=chapter_index,
                    time_slot=plan.time_slot,
                    pov_character_id=plan.pov_character_id,
                    who_is_present=plan.who_is_present,
                    beats=plan.beats,
                    content=content_text,
                    usage_metadata={},
                )
                save_chapter(novel_id, record)

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
                    time_slot_override=req.time_slot_override or inferred_time_slot,
                    pov_character_id_override=req.pov_character_id_override,
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
    chapters_dir = get_chapters_dir(novel_id)
    if chapters_dir.exists():
        for p in sorted(chapters_dir.glob("*.json")):
            try:
                chap_idx = int(p.stem)
            except Exception:
                continue
            chap = load_chapter(novel_id, chap_idx)
            if not chap:
                continue
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
        chapters_dir = get_chapters_dir(novel_id)
        if chapters_dir.exists():
            for p in sorted(chapters_dir.glob("*.json")):
                try:
                    chap_idx = int(p.stem)
                except Exception:
                    continue
                chap = load_chapter(novel_id, chap_idx)
                if not chap:
                    continue
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
    return {"tags": agent.lore_loader.get_lore_tags(), "count": len(agent.lore_loader.get_lore_tags())}


@app.get("/api/lore/preview")
def get_lore_preview(tag: str, max_chars: int = 0):
    logger.info("preview tag=%s max_chars=%s", tag, max_chars)
    preview = agent.lore_loader.get_preview_by_tag(tag=tag, max_chars=max_chars)
    return {"tag": tag, "preview": preview}

