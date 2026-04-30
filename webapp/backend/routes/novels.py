from __future__ import annotations

import json
import os
import shutil
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from agents.lore.lore_runtime import regenerate_auto_lore_with_graph
from agents.novel import NovelAgent
from agents.persistence.event_plan_store import (
    delete_event_plan,
    list_event_plans,
    load_event_plan,
)
from agents.persistence.graph_tables import (
    ensure_graph_tables,
    load_character_entities,
    patch_new_event_timeline_next_edges,
    persist_chapter_artifacts,
    replace_timeline_next_edges_from_state,
    resolve_chapter_timeline_event_id,
    validate_timeline_event_id,
)
from agents.persistence.env_paths import get_outputs_root
from agents.persistence.storage import load_chapter, load_state, save_state, list_chapters
from agents.state.chapter_structure import build_locked_structure_card, evaluate_structure_gate
from agents.state.consistency_audit import build_consistency_audit
from agents.state.shadow_director import build_shadow_director_package
from agents.state.state_models import Beat, ChapterPlan, ChapterRecord, CharacterPresence
from agents.text_utils import resolve_novel_outputs_dir
from webapp.backend.deps import agent, logger
from webapp.backend.domain.novel_lore_tags import normalize_novel_lore_tags
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
from webapp.backend.services.auto_lore import (
    build_auto_lore_docs_via_graph_rewrite,
    generate_auto_lore_for_novel,
    read_auto_lore_manifest,
    validate_regen_docs_constraints,
    write_auto_lore_docs_atomic,
)
from webapp.backend.services.novel_run import (
    build_chapter_plan_from_event,
    classify_event_plan_guard_error,
    infer_stream_error_code,
    require_bound_timeline_event_exists,
    require_event_plan_for_event,
    require_existing_event_binding,
    unwrap_chapter_plan_payload,
)
from webapp.backend.schemas import (
    AutoLoreRegenerateRequest,
    CreateNovelRequest,
    EventPlanGenerateRequest,
    NovelTagsUpdateRequest,
    NovelUpdateRequest,
    RunModeRequest,
)
from webapp.backend.ipc_chapter_writer import stream_write_chapter_text_ipc
from webapp.backend.sse import sse_pack

router = APIRouter(tags=["novels"])


AUTO_LORE_PREFIX = "自动生成/"
AUTO_LORE_FILE_SPECS = [
    "00_项目说明.md",
    "01_世界观骨架.md",
    "02_角色与关系草案.md",
    "03_连载主线与伏笔.md",
]


def _norm_tag(tag: str) -> str:
    return str(tag or "").replace("\\", "/").strip().strip("/")


def _is_auto_lore_tag(tag: str) -> bool:
    return _norm_tag(tag).startswith(AUTO_LORE_PREFIX)


def _is_auto_lore_tag_for_novel(tag: str, novel_id: str) -> bool:
    prefix = f"{AUTO_LORE_PREFIX}{novel_id}/"
    return _norm_tag(tag).startswith(prefix)


def _normalize_novel_lore_tags(
    *,
    novel_id: str,
    tags: List[str],
    ensure_auto_tags: Optional[List[str]] = None,
) -> List[str]:
    return normalize_novel_lore_tags(
        novel_id=novel_id,
        tags=tags,
        ensure_auto_tags=ensure_auto_tags,
    )


def _infer_stream_error_code(exc: Exception) -> str:
    return infer_stream_error_code(exc)


def _use_ipc_for_write_stream() -> bool:
    flag = str(os.getenv("WEBAPP_ENABLE_IPC_WRITE_STREAM", "")).strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _require_existing_event_binding(req: RunModeRequest) -> str:
    return require_existing_event_binding(req)


def _require_event_plan_for_event(novel_id: str, event_id: str):
    return require_event_plan_for_event(novel_id, event_id)


def _require_bound_timeline_event_exists(novel_id: str, event_id: str) -> str:
    return require_bound_timeline_event_exists(novel_id, event_id)


def _event_plan_guard_http_detail(exc: Exception) -> str:
    code, msg = classify_event_plan_guard_error(exc)
    return f"[{code}] {msg}"


def _build_chapter_plan_from_event(
    *,
    chapter_index: int,
    req: RunModeRequest,
    inferred_time_slot: Optional[str],
    st,
    event_plan_rec,
    pov_ids: List[str],
) -> ChapterPlan:
    return build_chapter_plan_from_event(
        chapter_index=chapter_index,
        req=req,
        inferred_time_slot=inferred_time_slot,
        st=st,
        event_plan_rec=event_plan_rec,
        pov_ids=pov_ids,
    )


def _unwrap_chapter_plan_payload(payload: Any) -> Dict[str, Any]:
    return unwrap_chapter_plan_payload(payload)


def _auto_lore_manifest_path(novel_id: str):
    return STORAGE_NOVELS_DIR / novel_id / "auto_lore_manifest.json"


def _safe_stem_text(v: str) -> str:
    s = "".join(ch for ch in str(v or "").strip() if ch.isalnum() or ch in ("_", "-", " ", "·", "."))
    return s.strip()[:48] or "untitled"


def _normalize_auto_lore_filename(name: str) -> str:
    fn = _safe_stem_text(name).replace(" ", "_").strip()
    if not fn:
        fn = "untitled"
    # 去掉末尾多余点，避免 ".md." 一类路径
    fn = fn.rstrip(".")
    if not fn.lower().endswith(".md"):
        fn = f"{fn}.md"
    # 兼容历史异常：xxx.md.md -> xxx.md
    while fn.lower().endswith(".md.md"):
        fn = fn[:-3]
    return fn


def _build_auto_lore_docs(
    *,
    novel_id: str,
    novel_title: str,
    start_time_slot: str,
    pov_character_id: str,
    selected_tags: List[str],
    brief: str,
) -> List[Dict[str, str]]:
    root = f"自动生成/{novel_id}"
    tag_hint = "、".join(selected_tags[:8]) if selected_tags else "（当前未勾选其他设定）"
    title_line = novel_title or "未命名小说"
    slot_line = start_time_slot or "未指定时间段"
    pov_line = pov_character_id or "未指定视角角色"
    brief_line = brief or "无额外说明。"
    files = [
        {
            "filename": "00_项目说明.md",
            "body": (
                f"# 自动设定包（{title_line}）\n\n"
                f"- 小说ID：`{novel_id}`\n"
                f"- 起始时间段：{slot_line}\n"
                f"- 起始视角：{pov_line}\n"
                f"- 创建时已勾选标签：{tag_hint}\n\n"
                "## 说明\n"
                "本目录内容由系统在创建小说时自动生成，可直接编辑。建议保留文件名，便于后续追踪。\n"
            ),
        },
        {
            "filename": "01_世界观骨架.md",
            "body": (
                f"# 世界观骨架 · {title_line}\n\n"
                "## 时代与环境\n"
                f"- 当前起点：{slot_line}\n"
                "- 时代技术层级：\n"
                "- 社会秩序与禁忌：\n"
                "- 资源与冲突稀缺点：\n\n"
                "## 本书核心矛盾\n"
                "- 主矛盾：\n"
                "- 次矛盾：\n"
                "- 触发事件：\n\n"
                "## 作者补充意图\n"
                f"{brief_line}\n"
            ),
        },
        {
            "filename": "02_角色与关系草案.md",
            "body": (
                f"# 角色与关系草案 · {title_line}\n\n"
                "## 主视角\n"
                f"- 角色ID：{pov_line}\n"
                "- 当前目标：\n"
                "- 隐性动机：\n"
                "- 风险与弱点：\n\n"
                "## 关键他者\n"
                "- 角色A：与主视角关系 / 利益冲突 / 可触发事件\n"
                "- 角色B：与主视角关系 / 利益冲突 / 可触发事件\n\n"
                "## 关系变化触发清单\n"
                "- 关系突变前置事件：\n"
                "- 关系逆转关键台词或行动：\n"
            ),
        },
        {
            "filename": "03_连载主线与伏笔.md",
            "body": (
                f"# 连载主线与伏笔 · {title_line}\n\n"
                "## 三段式主线\n"
                "- 第一阶段（铺设）：\n"
                "- 第二阶段（对抗）：\n"
                "- 第三阶段（回收）：\n\n"
                "## 伏笔池（建议至少3条）\n"
                "1. 伏笔内容：\n"
                "   - 埋设章节：\n"
                "   - 回收目标章节：\n"
                "2. 伏笔内容：\n"
                "   - 埋设章节：\n"
                "   - 回收目标章节：\n"
                "3. 伏笔内容：\n"
                "   - 埋设章节：\n"
                "   - 回收目标章节：\n"
            ),
        },
    ]
    docs: List[Dict[str, str]] = []
    for i, it in enumerate(files):
        expected = AUTO_LORE_FILE_SPECS[i] if i < len(AUTO_LORE_FILE_SPECS) else str(it["filename"])
        fn = _normalize_auto_lore_filename(expected)
        rel = f"{root}/{fn}"
        docs.append({"relative_path": rel, "tag": rel[:-3], "content": it["body"]})
    return docs


def _write_auto_lore_docs(
    *,
    novel_id: str,
    docs: List[Dict[str, str]],
    overwrite: bool,
) -> Dict[str, Any]:
    base = agent.lore_loader.data_path
    generated: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []
    for d in docs:
        rel = str(d.get("relative_path") or "").replace("\\", "/").strip()
        if not rel:
            continue
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        exists = path.exists()
        if exists and (not overwrite):
            skipped.append({"relative_path": rel, "tag": str(d.get("tag") or "")})
            continue
        path.write_text(str(d.get("content") or "").strip() + "\n", encoding="utf-8")
        generated.append({"relative_path": rel, "tag": str(d.get("tag") or "")})

    payload = {
        "novel_id": novel_id,
        "generated": generated,
        "skipped": skipped,
        "count": len(generated),
        "updated_at": str(uuid4()),
    }
    mf = _auto_lore_manifest_path(novel_id)
    mf.parent.mkdir(parents=True, exist_ok=True)
    mf.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _collect_existing_auto_lore_docs(novel_id: str) -> List[Dict[str, str]]:
    base = agent.lore_loader.data_path / "自动生成" / novel_id
    rows: List[Dict[str, str]] = []
    if not base.exists():
        return rows
    for fp in base.rglob("*.md"):
        if not fp.is_file():
            continue
        rel = fp.relative_to(agent.lore_loader.data_path).as_posix()
        rows.append(
            {
                "relative_path": rel,
                "filename": fp.name,
                "content": fp.read_text(encoding="utf-8"),
            }
        )
    rows.sort(key=lambda x: str(x.get("relative_path", "")))
    return rows


def _build_auto_lore_docs_via_graph_rewrite(
    *,
    novel_id: str,
    novel_title: str,
    brief: str,
) -> List[Dict[str, str]]:
    return build_auto_lore_docs_via_graph_rewrite(
        novel_id=novel_id,
        novel_title=novel_title,
        brief=brief,
        rewrite_fn=regenerate_auto_lore_with_graph,
    )


def _write_auto_lore_docs_atomic(
    *,
    novel_id: str,
    docs: List[Dict[str, str]],
) -> Dict[str, Any]:
    return write_auto_lore_docs_atomic(
        novel_id=novel_id,
        docs=docs,
    )


def _validate_regen_docs_constraints(novel_id: str, docs: List[Dict[str, str]]) -> None:
    validate_regen_docs_constraints(novel_id, docs)


def _read_auto_lore_manifest(novel_id: str) -> Dict[str, Any]:
    return read_auto_lore_manifest(novel_id)


def _generate_auto_lore_for_novel(
    *,
    novel_id: str,
    novel_title: str,
    start_time_slot: str,
    pov_character_id: str,
    lore_tags: List[str],
    brief: str,
    overwrite: bool,
) -> Dict[str, Any]:
    return generate_auto_lore_for_novel(
        novel_id=novel_id,
        novel_title=novel_title,
        start_time_slot=start_time_slot,
        pov_character_id=pov_character_id,
        lore_tags=lore_tags,
        brief=brief,
        overwrite=overwrite,
    )


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


def _build_shadow_director(
    *,
    novel_id: str,
    req: RunModeRequest,
    inferred_time_slot: Optional[str],
    timeline_focus_id: Optional[str],
    structure_gate: Optional[Dict[str, Any]],
    pov_ids: List[str],
) -> Optional[Dict[str, Any]]:
    if req.mode not in {"plan_only", "write_chapter", "revise_chapter", "expand_chapter"}:
        return None
    st = load_state(novel_id)
    if not st:
        return None
    return build_shadow_director_package(
        state=st,
        user_task=req.user_task,
        inferred_time_slot=inferred_time_slot,
        timeline_focus_id=timeline_focus_id,
        pov_ids=list(pov_ids or []),
        existing_supporting=list(req.supporting_character_ids or []),
        structure_card=(structure_gate.get("card") if structure_gate else None),
    )


def _merge_shadow_guidance(
    raw: Optional[Dict[str, Any]],
    shadow_director: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    out = dict(raw or {})
    if not shadow_director or not isinstance(shadow_director, dict):
        return out or None
    sug = shadow_director.get("suggestions")
    if not isinstance(sug, dict):
        return out or None
    if not str(out.get("conflict_type") or "").strip():
        out["conflict_type"] = str(sug.get("conflict_type") or "").strip()
    if not str(out.get("foreshadow_target") or "").strip():
        out["foreshadow_target"] = str(sug.get("foreshadow_target") or "").strip()
    rows = out.get("supporting_characters")
    if not isinstance(rows, list) or (not rows):
        out["supporting_characters"] = list(sug.get("supporting_characters") or [])
    return out or None


def _auto_rejudge_controls(
    *,
    novel_id: str,
    req: RunModeRequest,
    base_pov_ids: List[str],
    shadow_director: Optional[Dict[str, Any]],
    event_plan_rec: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    自动重判（手动优先）：
    - POV: 用户未填时，按 event plan + user_task + continuity 评分选 1 个
    - 配角: 用户未填时，复用 shadow director 推荐
    - guidance: 用户未填字段时，补影子编导冲突/伏笔建议
    """
    effective_pov_ids = [str(x).strip() for x in (base_pov_ids or []) if str(x).strip()]
    raw_supporting = [str(x).strip() for x in (req.supporting_character_ids or []) if str(x).strip()]
    effective_supporting = list(raw_supporting)

    st = load_state(novel_id)
    if (not effective_pov_ids) and st:
        event_text = ""
        if event_plan_rec is not None and getattr(event_plan_rec, "plan", None) is not None:
            p = event_plan_rec.plan
            event_text = " ".join(
                [
                    str(getattr(p, "objective", "") or ""),
                    str(getattr(p, "conflict", "") or ""),
                    " ".join([str(x or "") for x in (getattr(p, "progression", []) or [])]),
                    " ".join([str(x or "") for x in (getattr(p, "turning_points", []) or [])]),
                    str(getattr(p, "resolution_target", "") or ""),
                ]
            ).lower()
        task_text = str(req.user_task or "").lower()
        best_id = ""
        best_score = -1
        for c in st.characters or []:
            cid = str(getattr(c, "character_id", "") or "").strip()
            cname = str(getattr(c, "name", "") or "").strip()
            if not cid:
                continue
            score = 0
            if cid and cid.lower() in event_text:
                score += 3
            if cname and cname.lower() in event_text:
                score += 3
            if cid and cid.lower() in task_text:
                score += 2
            if cname and cname.lower() in task_text:
                score += 2
            if cid == str(st.continuity.pov_character_id or "").strip():
                score += 1
            if score > best_score:
                best_score = score
                best_id = cid
        if not best_id:
            best_id = str(st.continuity.pov_character_id or "").strip()
        if not best_id and (st.characters or []):
            best_id = str(getattr(st.characters[0], "character_id", "") or "").strip()
        if best_id:
            effective_pov_ids = [best_id]

    if (not effective_supporting) and isinstance(shadow_director, dict):
        sug = shadow_director.get("suggestions")
        rows = sug.get("supporting_characters") if isinstance(sug, dict) else None
        if isinstance(rows, list):
            picked: List[str] = []
            for it in rows:
                if not isinstance(it, dict):
                    continue
                sid = str(it.get("id") or "").strip()
                if sid and (sid not in picked) and (sid not in effective_pov_ids):
                    picked.append(sid)
            effective_supporting = picked

    raw_guidance = req.shadow_director_guidance if isinstance(req.shadow_director_guidance, dict) else None
    effective_guidance = _merge_shadow_guidance(raw_guidance, shadow_director)
    return {
        "effective_pov_ids": effective_pov_ids,
        "effective_supporting_character_ids": effective_supporting,
        "effective_shadow_director_guidance": effective_guidance,
        "manual_pov": bool(base_pov_ids),
        "manual_supporting": bool(raw_supporting),
    }


def _event_plan_binding_payload(event_plan_rec: Optional[Any]) -> Dict[str, Any]:
    if not event_plan_rec:
        return {}
    plan = getattr(event_plan_rec, "plan", None)
    return {
        "event_id": str(getattr(event_plan_rec, "event_id", "") or "").strip(),
        "event_plan_id": str(getattr(event_plan_rec, "event_plan_id", "") or "").strip(),
        "time_slot": str(getattr(plan, "time_slot", "") or "").strip() if plan else "",
        "objective": str(getattr(plan, "objective", "") or "").strip() if plan else "",
        "conflict": str(getattr(plan, "conflict", "") or "").strip() if plan else "",
        "progression_count": len(getattr(plan, "progression", []) or []) if plan else 0,
    }


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


@router.patch("/{novel_id}")
def update_novel(novel_id: str, req: NovelUpdateRequest):
    state = load_state(novel_id)
    if not state:
        raise HTTPException(status_code=404, detail="novel not found")
    title = str(req.novel_title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="novel_title is required")
    state.meta.novel_title = title
    save_state(novel_id, state)
    return {"ok": True, "novel_id": novel_id, "novel_title": title}


@router.patch("/{novel_id}/lore_tags")
def update_novel_lore_tags(novel_id: str, req: NovelTagsUpdateRequest):
    state = load_state(novel_id)
    if not state:
        raise HTTPException(status_code=404, detail="novel not found")
    cleaned = _normalize_novel_lore_tags(novel_id=novel_id, tags=[str(t or "") for t in (req.lore_tags or [])])
    state.meta.lore_tags = cleaned
    save_state(novel_id, state)
    return {"ok": True, "novel_id": novel_id, "lore_tags": cleaned, "count": len(cleaned)}


@router.delete("/{novel_id}")
def delete_novel(novel_id: str):
    # 仅允许删除 storage/novels 下该小说目录，避免误删
    target = (STORAGE_NOVELS_DIR / novel_id).resolve()
    base = STORAGE_NOVELS_DIR.resolve()
    if str(target) == str(base) or (base not in target.parents):
        raise HTTPException(status_code=400, detail="invalid novel_id")
    if not target.exists():
        raise HTTPException(status_code=404, detail="novel not found")
    shutil.rmtree(target, ignore_errors=False)
    # 同步清理该小说的自动设定目录，避免 lores 下历史目录持续累积
    auto_root = agent.lore_loader.data_path / "自动生成" / novel_id
    if auto_root.exists():
        shutil.rmtree(auto_root, ignore_errors=True)
    return {"ok": True, "novel_id": novel_id}


@router.post("")
def create_novel(req: CreateNovelRequest):
    novel_id = str(uuid4())
    title = str(req.novel_title or "").strip() or "未命名小说"
    start_slot = str(req.start_time_slot or "").strip()
    pov_id = str(req.pov_character_id or "").strip()
    picked_tags = _normalize_novel_lore_tags(
        novel_id=novel_id,
        tags=[str(t or "") for t in (req.lore_tags or [])],
    )
    agent.create_novel_stub(
        novel_id=novel_id,
        novel_title=title,
        start_time_slot=start_slot or None,
        pov_character_id=pov_id or None,
        lore_tags=picked_tags,
    )

    auto_manifest: Dict[str, Any] = {"generated": [], "count": 0}
    if bool(req.auto_generate_lore):
        try:
            auto_manifest = _generate_auto_lore_for_novel(
                novel_id=novel_id,
                novel_title=title,
                start_time_slot=start_slot,
                pov_character_id=pov_id,
                lore_tags=picked_tags,
                brief=str(req.auto_lore_brief or "").strip(),
                overwrite=True,
            )
        except Exception as e:
            logger.warning("auto lore generation failed for novel_id=%s: %s", novel_id, e)

    try:
        st_now = load_state(novel_id)
        if st_now:
            generated_tags = [
                str(x.get("tag") or "").strip()
                for x in (auto_manifest.get("generated") or [])
                if isinstance(x, dict)
            ]
            st_now.meta.lore_tags = _normalize_novel_lore_tags(
                novel_id=novel_id,
                tags=[str(t or "") for t in (st_now.meta.lore_tags or [])],
                ensure_auto_tags=generated_tags,
            )
            save_state(novel_id, st_now)
    except Exception as e:
        logger.warning("normalize lore tags failed for novel_id=%s: %s", novel_id, e)

    if req.initial_user_task and req.initial_user_task.strip():
        try:
            agent.init_state(
                novel_id=novel_id,
                user_task=req.initial_user_task,
                lore_tags=picked_tags,
            )
        except Exception:
            pass

    return {
        "novel_id": novel_id,
        "auto_lore": auto_manifest,
    }


@router.get("/{novel_id}/auto_lore")
def get_auto_lore(novel_id: str):
    st = load_state(novel_id)
    if not st:
        raise HTTPException(status_code=404, detail="novel not found")
    return _read_auto_lore_manifest(novel_id)


@router.post("/{novel_id}/auto_lore/regenerate")
def regenerate_auto_lore(novel_id: str, req: AutoLoreRegenerateRequest):
    st = load_state(novel_id)
    if not st:
        raise HTTPException(status_code=404, detail="novel not found")
    try:
        docs = _build_auto_lore_docs_via_graph_rewrite(
            novel_id=novel_id,
            novel_title=str(st.meta.novel_title or "").strip() or "未命名小说",
            brief=str(req.brief or "").strip(),
        )
        _validate_regen_docs_constraints(novel_id, docs)
        payload = _write_auto_lore_docs_atomic(
            novel_id=novel_id,
            docs=docs,
        )
    except Exception as e:
        logger.exception("regenerate auto lore failed novel_id=%s", novel_id)
        raise HTTPException(status_code=400, detail=f"重生成失败，未覆盖任何文件：{e}") from None
    try:
        generated_tags = [
            str(x.get("tag") or "").strip()
            for x in (payload.get("generated") or [])
            if isinstance(x, dict)
        ]
        st.meta.lore_tags = _normalize_novel_lore_tags(
            novel_id=novel_id,
            tags=[str(t or "") for t in (st.meta.lore_tags or [])],
            ensure_auto_tags=generated_tags,
        )
        save_state(novel_id, st)
    except Exception as e:
        logger.warning("regenerate auto lore tags sync failed for novel_id=%s: %s", novel_id, e)
    return payload


@router.get("/{novel_id}/state")
def get_state(novel_id: str):
    state = load_state(novel_id)
    if not state:
        raise HTTPException(status_code=404, detail="novel not found")
    payload = state.model_dump(mode="json")
    title = str(state.meta.novel_title or "未命名小说")
    out_dir = resolve_novel_outputs_dir(title, novel_id)
    payload["outputs"] = {
        "root_dir": str(get_outputs_root().resolve()),
        "novel_subdir": str(out_dir).replace("\\", "/").rstrip("/").split("/")[-1],
        "novel_output_dir": out_dir,
    }
    return payload


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


@router.post("/{novel_id}/event_plan")
def generate_event_plan(novel_id: str, req: EventPlanGenerateRequest):
    st = load_state(novel_id)
    if not st:
        raise HTTPException(status_code=404, detail="novel not found")
    event_id = str(req.event_id or "").strip()
    if not event_id.startswith("ev:timeline:"):
        raise HTTPException(status_code=400, detail="event_id must be ev:timeline:*")
    try:
        _require_bound_timeline_event_exists(novel_id, event_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=_event_plan_guard_http_detail(e)) from None
    try:
        rec = agent.plan_event(
            novel_id=novel_id,
            event_id=event_id,
            user_task=str(req.user_task or "").strip() or "生成该事件计划",
            lore_tags=req.lore_tags,
        )
    except Exception as e:
        msg = str(e or "")
        low = msg.lower()
        if ("validation error" in low or "field required" in low) and (
            "event_id" in low or "time_slot" in low
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "事件计划生成失败：模型返回结构不完整（缺少 event_id/time_slot）。"
                    "已中止保存，请重试。"
                ),
            ) from None
        raise HTTPException(status_code=400, detail=f"事件计划生成失败：{msg}") from None
    return rec.model_dump(mode="json")


@router.get("/{novel_id}/event_plans")
def get_event_plans(novel_id: str):
    st = load_state(novel_id)
    if not st:
        raise HTTPException(status_code=404, detail="novel not found")
    rows = list_event_plans(novel_id)
    return {"novel_id": novel_id, "rows": [x.model_dump(mode="json") for x in rows], "count": len(rows)}


@router.get("/{novel_id}/event_plan/{event_id}")
def get_event_plan(novel_id: str, event_id: str):
    st = load_state(novel_id)
    if not st:
        raise HTTPException(status_code=404, detail="novel not found")
    rec = load_event_plan(novel_id, event_id)
    if not rec:
        raise HTTPException(status_code=404, detail="event plan not found")
    return rec.model_dump(mode="json")


@router.delete("/{novel_id}/event_plan/{event_id}")
def remove_event_plan(novel_id: str, event_id: str):
    st = load_state(novel_id)
    if not st:
        raise HTTPException(status_code=404, detail="novel not found")
    ok = delete_event_plan(novel_id, event_id)
    if not ok:
        raise HTTPException(status_code=404, detail="event plan not found")
    return {"novel_id": novel_id, "event_id": event_id, "deleted": True}


@router.post("/{novel_id}/run")
def run_mode(novel_id: str, req: RunModeRequest) -> Dict[str, Any]:
    inferred = infer_time_slot(novel_id, req)
    timeline_focus_id = req_timeline_focus_id(req)
    manual_time_slot = bool((req.time_slot_override or "").strip())
    pov_ids = list(req.pov_character_ids_override or [])
    if (not pov_ids) and req.pov_character_id_override:
        pov_ids = [req.pov_character_id_override]
    st0 = load_state(novel_id)
    pre_chapter_index = req.chapter_index or ((st0.meta.current_chapter_index + 1) if st0 else 1)
    structure_gate = _build_structure_gate(
        novel_id=novel_id,
        req=req,
        inferred_time_slot=inferred,
        chapter_index=int(pre_chapter_index),
        timeline_focus_id=timeline_focus_id,
    )
    shadow_director = _build_shadow_director(
        novel_id=novel_id,
        req=req,
        inferred_time_slot=inferred,
        timeline_focus_id=timeline_focus_id,
        structure_gate=structure_gate,
        pov_ids=pov_ids,
    )
    event_plan_rec = None
    effective = {
        "effective_pov_ids": list(pov_ids),
        "effective_supporting_character_ids": [str(x).strip() for x in (req.supporting_character_ids or []) if str(x).strip()],
        "effective_shadow_director_guidance": (
            req.shadow_director_guidance if isinstance(req.shadow_director_guidance, dict) else None
        ),
        "manual_pov": bool(pov_ids),
        "manual_supporting": bool(req.supporting_character_ids),
    }
    try:
        if req.mode == "plan_only":
            raise ValueError("event-only mode: chapter plan_only is disabled")
        if req.mode in {"write_chapter", "revise_chapter", "expand_chapter"}:
            event_id = _require_existing_event_binding(req)
            _require_bound_timeline_event_exists(novel_id, event_id)
            event_plan_rec = _require_event_plan_for_event(novel_id, event_id)
            effective = _auto_rejudge_controls(
                novel_id=novel_id,
                req=req,
                base_pov_ids=pov_ids,
                shadow_director=shadow_director,
                event_plan_rec=event_plan_rec,
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail=_event_plan_guard_http_detail(e))
    req_effective = req.model_copy(deep=True)
    req_effective.supporting_character_ids = list(effective["effective_supporting_character_ids"])
    req_effective.shadow_director_guidance = effective["effective_shadow_director_guidance"]
    llm_user_task = build_llm_user_task(
        novel_id,
        req.user_task,
        req_effective,
        inferred,
        list(effective["effective_pov_ids"]),
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
            "shadow_director": shadow_director,
        }
    if req.mode in {"plan_only", "write_chapter", "revise_chapter", "expand_chapter"}:
        try:
            prebuild_chapter_graph_records(
                novel_id=novel_id,
                req=req_effective,
                chapter_index=int(pre_chapter_index),
                inferred_time_slot=inferred,
                pov_ids=list(effective["effective_pov_ids"]),
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
            pov_character_ids_override=list(effective["effective_pov_ids"]),
            supporting_character_ids=list(effective["effective_supporting_character_ids"]),
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
    if shadow_director:
        resp["shadow_director"] = shadow_director
    if req.mode in {"write_chapter", "revise_chapter", "expand_chapter"}:
        resp["event_plan_binding"] = _event_plan_binding_payload(event_plan_rec)
        resp["auto_rejudge"] = {
            "effective_pov_ids": list(effective["effective_pov_ids"]),
            "effective_supporting_character_ids": list(effective["effective_supporting_character_ids"]),
            "effective_shadow_director_guidance": effective["effective_shadow_director_guidance"],
            "manual_pov": bool(effective["manual_pov"]),
            "manual_supporting": bool(effective["manual_supporting"]),
            "event_plan_id": (event_plan_rec.event_plan_id if event_plan_rec else None),
        }
    state_obj = load_state(novel_id)
    resp["state"] = state_obj.model_dump(mode="json") if state_obj else None
    if req.mode in {"write_chapter", "revise_chapter", "expand_chapter"} and result.chapter_index and state_obj:
        chapter_row = load_chapter(novel_id, int(result.chapter_index))
        if chapter_row:
            prev_chapter = load_chapter(novel_id, int(result.chapter_index) - 1) if int(result.chapter_index) > 1 else None
            resp["consistency_audit"] = build_consistency_audit(
                state=state_obj,
                chapter=chapter_row,
                mode=req.mode,
                previous_chapter=prev_chapter,
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
    st0 = load_state(novel_id)
    pre_chapter_index = req.chapter_index or ((st0.meta.current_chapter_index + 1) if st0 else 1)
    structure_gate = _build_structure_gate(
        novel_id=novel_id,
        req=req,
        inferred_time_slot=inferred,
        chapter_index=int(pre_chapter_index),
        timeline_focus_id=timeline_focus_id,
    )
    shadow_director = _build_shadow_director(
        novel_id=novel_id,
        req=req,
        inferred_time_slot=inferred,
        timeline_focus_id=timeline_focus_id,
        structure_gate=structure_gate,
        pov_ids=pov_ids,
    )
    event_plan_rec = None
    effective = {
        "effective_pov_ids": list(pov_ids),
        "effective_supporting_character_ids": [str(x).strip() for x in (req.supporting_character_ids or []) if str(x).strip()],
        "effective_shadow_director_guidance": (
            req.shadow_director_guidance if isinstance(req.shadow_director_guidance, dict) else None
        ),
        "manual_pov": bool(pov_ids),
        "manual_supporting": bool(req.supporting_character_ids),
    }
    if req.mode == "plan_only":
        raise HTTPException(status_code=400, detail="event-only mode: chapter plan_only is disabled")
    try:
        if req.mode in {"write_chapter", "revise_chapter", "expand_chapter"}:
            event_id = _require_existing_event_binding(req)
            _require_bound_timeline_event_exists(novel_id, event_id)
            event_plan_rec = _require_event_plan_for_event(novel_id, event_id)
            effective = _auto_rejudge_controls(
                novel_id=novel_id,
                req=req,
                base_pov_ids=pov_ids,
                shadow_director=shadow_director,
                event_plan_rec=event_plan_rec,
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail=_event_plan_guard_http_detail(e))
    req_effective = req.model_copy(deep=True)
    req_effective.supporting_character_ids = list(effective["effective_supporting_character_ids"])
    req_effective.shadow_director_guidance = effective["effective_shadow_director_guidance"]
    llm_user_task = build_llm_user_task(
        novel_id,
        req.user_task,
        req_effective,
        inferred,
        list(effective["effective_pov_ids"]),
    )
    try:
        out = agent.preview_input(
            novel_id=novel_id,
            mode=req.mode,
            user_task=llm_user_task,
            chapter_index=req.chapter_index,
            time_slot_override=inferred,
            manual_time_slot=manual_time_slot,
            pov_character_ids_override=list(effective["effective_pov_ids"]),
            supporting_character_ids=list(effective["effective_supporting_character_ids"]),
            lore_tags=req.lore_tags,
            timeline_event_focus_id=timeline_focus_id,
            omit_world_timeline=uses_new_timeline_event_for_chapter(req),
        )
        if structure_gate:
            out["structure_gate"] = structure_gate
        if shadow_director:
            out["shadow_director"] = shadow_director
        if req.mode in {"write_chapter", "revise_chapter", "expand_chapter"}:
            out["event_plan_binding"] = _event_plan_binding_payload(event_plan_rec)
            out["auto_rejudge"] = {
                "effective_pov_ids": list(effective["effective_pov_ids"]),
                "effective_supporting_character_ids": list(effective["effective_supporting_character_ids"]),
                "effective_shadow_director_guidance": effective["effective_shadow_director_guidance"],
                "manual_pov": bool(effective["manual_pov"]),
                "manual_supporting": bool(effective["manual_supporting"]),
                "event_plan_id": (event_plan_rec.event_plan_id if event_plan_rec else None),
            }
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

        request_id = uuid4().hex
        current_phase = "start"

        def _pack_phase(name: str, **payload: Any) -> bytes:
            nonlocal current_phase
            current_phase = name
            body = {"name": name, "request_id": request_id}
            body.update(payload)
            return sse_pack("phase", body)

        yield sse_pack("start", {"novel_id": novel_id, "mode": req.mode, "request_id": request_id, "phase": "start"})

        inferred = infer_time_slot(novel_id, req)
        timeline_focus_id = req_timeline_focus_id(req)
        manual_time_slot = bool((req.time_slot_override or "").strip())
        pov_ids = list(req.pov_character_ids_override or [])
        if (not pov_ids) and req.pov_character_id_override:
            pov_ids = [req.pov_character_id_override]
        effective = {
            "effective_pov_ids": list(pov_ids),
            "effective_supporting_character_ids": [str(x).strip() for x in (req.supporting_character_ids or []) if str(x).strip()],
            "effective_shadow_director_guidance": (
                req.shadow_director_guidance if isinstance(req.shadow_director_guidance, dict) else None
            ),
            "manual_pov": bool(pov_ids),
            "manual_supporting": bool(req.supporting_character_ids),
        }
        llm_user_task = build_llm_user_task(
            novel_id,
            req.user_task,
            req,
            inferred,
            list(effective["effective_pov_ids"]),
        )
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
        shadow_director = _build_shadow_director(
            novel_id=novel_id,
            req=req,
            inferred_time_slot=inferred,
            timeline_focus_id=timeline_focus_id,
            structure_gate=structure_gate,
            pov_ids=pov_ids,
        )
        if structure_gate and structure_gate.get("needs_ack") and (not req.structure_risk_ack):
            yield sse_pack(
                "done",
                {
                    "novel_id": novel_id,
                    "request_id": request_id,
                    "phase": "done",
                    "mode": req.mode,
                    "chapter_index": int(pre_chapter_index),
                    "state_updated": False,
                    "blocked": True,
                    "block_type": "structure_gate",
                    "structure_gate": structure_gate,
                    "shadow_director": shadow_director,
                    "usage_metadata": {},
                    "content": None,
                    "plan": None,
                    "state": (st0.model_dump(mode="json") if st0 else None),
                    "next_status": None,
                    "auto_rejudge": (
                        {
                            "effective_pov_ids": list(effective["effective_pov_ids"]),
                            "effective_supporting_character_ids": list(effective["effective_supporting_character_ids"]),
                            "effective_shadow_director_guidance": effective["effective_shadow_director_guidance"],
                            "manual_pov": bool(effective["manual_pov"]),
                            "manual_supporting": bool(effective["manual_supporting"]),
                        }
                        if req.mode in {"write_chapter", "revise_chapter", "expand_chapter"}
                        else None
                    ),
                },
            )
            return
        if req.mode == "plan_only":
            raise ValueError("event-only mode: chapter plan_only is disabled")

        try:
            if req.mode in {"write_chapter", "revise_chapter", "expand_chapter"}:
                if await _disconnected():
                    logger.info("run_stream client disconnected early. novel_id=%s mode=%s", novel_id, req.mode)
                    return
                yield _pack_phase("planning")

                st = load_state(novel_id)
                if not st:
                    raise ValueError("novel not found")
                if not st.meta.initialized:
                    raise ValueError("state not initialized. please run init_state first")

                chapter_index = req.chapter_index or (st.meta.current_chapter_index + 1)
                bound_event_id = _require_existing_event_binding(req)
                _require_bound_timeline_event_exists(novel_id, bound_event_id)
                event_plan_rec = _require_event_plan_for_event(novel_id, bound_event_id)
                effective = _auto_rejudge_controls(
                    novel_id=novel_id,
                    req=req,
                    base_pov_ids=pov_ids,
                    shadow_director=shadow_director,
                    event_plan_rec=event_plan_rec,
                )
                req_effective = req.model_copy(deep=True)
                req_effective.supporting_character_ids = list(effective["effective_supporting_character_ids"])
                req_effective.shadow_director_guidance = effective["effective_shadow_director_guidance"]
                llm_user_task = build_llm_user_task(
                    novel_id,
                    req.user_task,
                    req_effective,
                    inferred,
                    list(effective["effective_pov_ids"]),
                )
                try:
                    prebuild_chapter_graph_records(
                        novel_id=novel_id,
                        req=req_effective,
                        chapter_index=int(chapter_index),
                        inferred_time_slot=inferred,
                        pov_ids=list(effective["effective_pov_ids"]),
                    )
                except Exception as e:
                    logger.warning("prebuild chapter graph records failed(stream): %s", e)
                plan = _build_chapter_plan_from_event(
                    chapter_index=int(chapter_index),
                    req=req_effective,
                    inferred_time_slot=inferred,
                    st=st,
                    event_plan_rec=event_plan_rec,
                    pov_ids=list(effective["effective_pov_ids"]),
                )
                inserted_timeline_eid = None
                yield sse_pack(
                    "plan_content",
                    {
                        "delta": json.dumps(
                            {
                                "event_plan_id": event_plan_rec.event_plan_id,
                                "event_id": event_plan_rec.event_id,
                                "objective": event_plan_rec.plan.objective,
                                "conflict": event_plan_rec.plan.conflict,
                            },
                            ensure_ascii=False,
                        )
                    },
                )

                use_ipc_stream = _use_ipc_for_write_stream()
                yield _pack_phase("writing", chapter_index=chapter_index, via=("ipc" if use_ipc_stream else "inproc"))
                parts: List[str] = []
                usage_meta: Dict[str, Any] = {}
                write_mode = "expand" if req.mode == "expand_chapter" else "generate"
                stream_iter = (
                    stream_write_chapter_text_ipc(
                        novel_id=novel_id,
                        plan=plan,
                        user_task=llm_user_task,
                        minimal_state_for_prompt=manual_time_slot,
                        lore_tags=req.lore_tags,
                        time_slot_hint=inferred,
                        pov_character_ids_override=list(effective["effective_pov_ids"]),
                        supporting_character_ids=list(effective["effective_supporting_character_ids"]),
                        llm_options=llm_opts,
                        timeline_event_focus_id=timeline_focus_id,
                        write_mode=write_mode,
                        event_plan=event_plan_rec.plan,
                        omit_world_timeline=omit_world_timeline,
                    )
                    if use_ipc_stream
                    else agent.write_chapter_text_stream(
                        novel_id=novel_id,
                        plan=plan,
                        user_task=llm_user_task,
                        minimal_state_for_prompt=manual_time_slot,
                        lore_tags=req.lore_tags,
                        time_slot_hint=inferred,
                        pov_character_ids_override=list(effective["effective_pov_ids"]),
                        supporting_character_ids=list(effective["effective_supporting_character_ids"]),
                        llm_options=llm_opts,
                        timeline_event_focus_id=timeline_focus_id,
                        write_mode=write_mode,
                        event_plan=event_plan_rec.plan,
                        omit_world_timeline=omit_world_timeline,
                    )
                )
                for item in stream_iter:
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
                yield _pack_phase("saving")
                next_state = plan.next_state
                record = ChapterRecord(
                    chapter_index=chapter_index,
                    chapter_preset_name=req.chapter_preset_name,
                    timeline_event_id=validate_timeline_event_id(next_state, timeline_focus_id),
                    source_event_plan_id=event_plan_rec.event_plan_id,
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
                    out_path = write_outputs_txt(title, chapter_index, content_text, novel_id=novel_id)
                    yield _pack_phase("outputs_written", path=out_path)
                except Exception as e:
                    logger.warning("Failed to write outputs txt (stream): %s", e)
                    yield _pack_phase("outputs_write_failed", error=str(e))

                next_status = ""
                try:
                    if await _disconnected():
                        logger.info(
                            "run_stream disconnected before next_status. novel_id=%s chapter=%s",
                            novel_id,
                            chapter_index,
                        )
                        return
                    yield _pack_phase("next_status")
                    next_status = agent.suggest_next_status(
                        novel_id=novel_id,
                        user_task=llm_user_task,
                        chapter_index=chapter_index,
                        latest_content=content_text,
                        llm_options=llm_opts,
                        timeline_event_focus_id=timeline_focus_id,
                    )
                    yield _pack_phase("next_status_done", has_text=bool((next_status or "").strip()))
                except Exception as e:
                    logger.warning("Failed to generate next_status (stream): %s", e)
                    yield _pack_phase("next_status_failed", error=str(e))

                st_done = load_state(novel_id)
                chapter_timeline_event_id = (
                    resolve_chapter_timeline_event_id(st_done, record) if st_done else None
                )
                consistency_audit = (
                    build_consistency_audit(
                        state=st_done,
                        chapter=record,
                        mode=req.mode,
                        previous_chapter=(load_chapter(novel_id, chapter_index - 1) if chapter_index > 1 else None),
                    )
                    if st_done
                    else None
                )

                yield sse_pack(
                    "done",
                    {
                        "novel_id": novel_id,
                        "request_id": request_id,
                        "phase": "done",
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
                        "shadow_director": shadow_director,
                        "event_plan_binding": _event_plan_binding_payload(event_plan_rec),
                        "auto_rejudge": {
                            "effective_pov_ids": list(effective["effective_pov_ids"]),
                            "effective_supporting_character_ids": list(effective["effective_supporting_character_ids"]),
                            "effective_shadow_director_guidance": effective["effective_shadow_director_guidance"],
                            "manual_pov": bool(effective["manual_pov"]),
                            "manual_supporting": bool(effective["manual_supporting"]),
                            "event_plan_id": event_plan_rec.event_plan_id,
                        },
                    },
                )
            elif req.mode == "optimize_suggestions":
                if await _disconnected():
                    return
                st_opt = load_state(novel_id)
                if not st_opt or not st_opt.meta.initialized:
                    raise ValueError("state not initialized. please run init_state first")
                yield _pack_phase("optimizing")
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
                        "request_id": request_id,
                        "phase": "done",
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
                yield _pack_phase("world_init")
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
                        "request_id": request_id,
                        "phase": "done",
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
                yield _pack_phase("running")
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
                        prev_chapter = load_chapter(novel_id, int(result.chapter_index) - 1) if int(result.chapter_index) > 1 else None
                        consistency_audit = build_consistency_audit(
                            state=state_obj,
                            chapter=chapter_row,
                            mode=req.mode,
                            previous_chapter=prev_chapter,
                        )
                yield sse_pack(
                    "done",
                    {
                        "novel_id": novel_id,
                        "request_id": request_id,
                        "phase": "done",
                        "mode": req.mode,
                        "chapter_index": result.chapter_index,
                        "state_updated": result.state_updated,
                        "usage_metadata": result.usage_metadata,
                        "content": result.content,
                        "plan": (result.plan.model_dump(mode="json") if result.plan else None),
                        "state": (state_obj.model_dump(mode="json") if state_obj else None),
                        "consistency_audit": consistency_audit,
                        "structure_gate": structure_gate,
                        "shadow_director": shadow_director,
                    },
                )
        except Exception as e:
            logger.exception("run_stream failed novel_id=%s mode=%s", novel_id, req.mode)
            if not await _disconnected():
                yield sse_pack(
                    "error",
                    {
                        "message": str(e),
                        "request_id": request_id,
                        "phase": current_phase,
                        "error_code": _infer_stream_error_code(e),
                    },
                )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
