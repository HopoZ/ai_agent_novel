from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agents.lore.lore_summary import get_lore_summary, load_cached_summary, source_hash_from_map
from webapp.backend.deps import agent, logger
from webapp.backend.schemas import BuildLoreSummaryRequest

router = APIRouter(tags=["lore"])


@router.post("/summary/build")
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


@router.get("/summary/{summary_id}")
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


@router.get("/tags")
def get_lore_tags():
    tags = agent.lore_loader.get_lore_tags()
    groups = agent.lore_loader.get_lore_tag_groups()
    return {"tags": tags, "groups": groups, "count": len(tags)}


@router.get("/preview")
def get_lore_preview(tag: str, max_chars: int = 0, compact: bool = False):
    logger.info("preview tag=%s max_chars=%s compact=%s", tag, max_chars, compact)
    if compact:
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
