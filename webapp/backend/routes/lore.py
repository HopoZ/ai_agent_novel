from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from agents.lore.lore_summary import get_lore_summary, load_cached_summary, source_hash_from_map
from agents.persistence.storage import load_state, save_state
from webapp.backend.deps import agent, logger
from webapp.backend.paths import STORAGE_NOVELS_DIR
from webapp.backend.schemas import (
    BuildLoreSummaryRequest,
    LoreTagBatchDeleteRequest,
    LoreTagBatchReplacePrefixRequest,
    LoreTagCreateRequest,
    LoreTagDeleteRequest,
    LoreTagRenameRequest,
    LoreTagUpdateContentRequest,
)

router = APIRouter(tags=["lore"])


def _clean_tag(tag: str) -> str:
    clean = str(tag or "").strip().replace("\\", "/").strip("/")
    if not clean:
        raise HTTPException(status_code=400, detail="tag is required")
    if ".." in clean.split("/"):
        raise HTTPException(status_code=400, detail="invalid tag path")
    if clean.lower().endswith(".md"):
        clean = clean[:-3]
    if not clean:
        raise HTTPException(status_code=400, detail="tag is required")
    return clean


def _tag_to_abs_path(tag: str) -> Path:
    root = Path(agent.lore_loader.data_path).resolve()
    target = (root / f"{tag}.md").resolve()
    if root not in target.parents:
        raise HTTPException(status_code=400, detail="invalid tag path")
    if target.name.lower() == "readme.md":
        raise HTTPException(status_code=400, detail="README.md is reserved")
    return target


def _clean_prefix(prefix: str) -> str:
    clean = str(prefix or "").strip().replace("\\", "/").strip("/")
    if ".." in clean.split("/"):
        raise HTTPException(status_code=400, detail="invalid prefix path")
    return clean


def _sync_novel_lore_tags(*, rename_map: dict[str, str] | None = None, removed: set[str] | None = None) -> int:
    rename_map = rename_map or {}
    removed = removed or set()
    changed_novels = 0
    if not STORAGE_NOVELS_DIR.exists():
        return 0
    for d in STORAGE_NOVELS_DIR.iterdir():
        if not d.is_dir():
            continue
        novel_id = d.name
        try:
            st = load_state(novel_id)
            if not st:
                continue
            old_tags = [str(t).strip() for t in (st.meta.lore_tags or []) if str(t).strip()]
            new_tags: list[str] = []
            seen: set[str] = set()
            changed = False
            for t in old_tags:
                if t in removed:
                    changed = True
                    continue
                mapped = rename_map.get(t, t)
                if mapped != t:
                    changed = True
                if (not mapped) or (mapped in seen):
                    continue
                seen.add(mapped)
                new_tags.append(mapped)
            if changed:
                st.meta.lore_tags = new_tags
                save_state(novel_id, st)
                changed_novels += 1
        except Exception:
            continue
    return changed_novels


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


@router.post("/tags")
def create_lore_tag(req: LoreTagCreateRequest):
    tag = _clean_tag(req.tag)
    p = _tag_to_abs_path(tag)
    if p.exists() and (not req.overwrite):
        raise HTTPException(status_code=409, detail="tag already exists")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(req.content or "").strip() + "\n", encoding="utf-8")
    return {"ok": True, "tag": tag, "relative_path": str(p.relative_to(agent.lore_loader.data_path).as_posix())}


@router.patch("/tags")
def rename_lore_tag(req: LoreTagRenameRequest):
    old_tag = _clean_tag(req.old_tag)
    new_tag = _clean_tag(req.new_tag)
    if old_tag == new_tag:
        return {"ok": True, "old_tag": old_tag, "new_tag": new_tag}
    old_p = _tag_to_abs_path(old_tag)
    new_p = _tag_to_abs_path(new_tag)
    if not old_p.exists():
        raise HTTPException(status_code=404, detail="old tag not found")
    if new_p.exists():
        raise HTTPException(status_code=409, detail="new tag already exists")
    new_p.parent.mkdir(parents=True, exist_ok=True)
    old_p.rename(new_p)
    changed_novels = _sync_novel_lore_tags(rename_map={old_tag: new_tag})
    return {"ok": True, "old_tag": old_tag, "new_tag": new_tag, "changed_novels": changed_novels}


@router.delete("/tags")
def delete_lore_tag(req: LoreTagDeleteRequest):
    tag = _clean_tag(req.tag)
    p = _tag_to_abs_path(tag)
    if not p.exists():
        raise HTTPException(status_code=404, detail="tag not found")
    p.unlink(missing_ok=False)
    changed_novels = _sync_novel_lore_tags(removed={tag})
    return {"ok": True, "tag": tag, "changed_novels": changed_novels}


@router.put("/tags/content")
def update_lore_tag_content(req: LoreTagUpdateContentRequest):
    tag = _clean_tag(req.tag)
    p = _tag_to_abs_path(tag)
    if not p.exists():
        raise HTTPException(status_code=404, detail="tag not found")
    p.write_text(str(req.content or "").strip() + "\n", encoding="utf-8")
    return {"ok": True, "tag": tag}


@router.post("/tags/batch_delete")
def batch_delete_lore_tags(req: LoreTagBatchDeleteRequest):
    cleaned_tags: list[str] = []
    seen: set[str] = set()
    for x in (req.tags or []):
        t = _clean_tag(str(x or ""))
        if t in seen:
            continue
        seen.add(t)
        cleaned_tags.append(t)
    if not cleaned_tags:
        raise HTTPException(status_code=400, detail="tags is required")
    deleted: list[str] = []
    skipped: list[str] = []
    for t in cleaned_tags:
        p = _tag_to_abs_path(t)
        if not p.exists():
            skipped.append(t)
            continue
        p.unlink(missing_ok=False)
        deleted.append(t)
    changed_novels = _sync_novel_lore_tags(removed=set(deleted))
    return {
        "ok": True,
        "deleted": deleted,
        "skipped": skipped,
        "count": len(deleted),
        "changed_novels": changed_novels,
    }


@router.post("/tags/batch_replace_prefix")
def batch_replace_prefix(req: LoreTagBatchReplacePrefixRequest):
    cleaned_tags: list[str] = []
    seen: set[str] = set()
    for x in (req.tags or []):
        t = _clean_tag(str(x or ""))
        if t in seen:
            continue
        seen.add(t)
        cleaned_tags.append(t)
    if not cleaned_tags:
        raise HTTPException(status_code=400, detail="tags is required")
    old_prefix = _clean_prefix(req.old_prefix)
    new_prefix = _clean_prefix(req.new_prefix)

    source_set = set(cleaned_tags)
    planned_pairs: list[tuple[str, str]] = []
    skipped: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    target_set: set[str] = set()

    for old_tag in cleaned_tags:
        if old_prefix:
            if old_tag == old_prefix:
                suffix = ""
            elif old_tag.startswith(f"{old_prefix}/"):
                suffix = old_tag[len(old_prefix) + 1 :]
            else:
                skipped.append({"tag": old_tag, "reason": "old_prefix_not_match"})
                continue
        else:
            suffix = old_tag
        parts = [p for p in [new_prefix, suffix] if p]
        new_tag = "/".join(parts).strip("/")
        if not new_tag:
            failed.append({"tag": old_tag, "reason": "target_empty"})
            continue
        if new_tag == old_tag:
            skipped.append({"tag": old_tag, "reason": "same_tag"})
            continue
        if new_tag in source_set:
            failed.append({"tag": old_tag, "reason": "target_is_source_tag"})
            continue
        if new_tag in target_set:
            failed.append({"tag": old_tag, "reason": "target_conflict_in_batch"})
            continue
        old_p = _tag_to_abs_path(old_tag)
        new_p = _tag_to_abs_path(new_tag)
        if not old_p.exists():
            skipped.append({"tag": old_tag, "reason": "source_not_found"})
            continue
        if new_p.exists():
            failed.append({"tag": old_tag, "reason": "target_exists"})
            continue
        target_set.add(new_tag)
        planned_pairs.append((old_tag, new_tag))

    moved: list[dict[str, str]] = []
    rename_map: dict[str, str] = {}
    for old_tag, new_tag in planned_pairs:
        old_p = _tag_to_abs_path(old_tag)
        new_p = _tag_to_abs_path(new_tag)
        new_p.parent.mkdir(parents=True, exist_ok=True)
        old_p.rename(new_p)
        moved.append({"old_tag": old_tag, "new_tag": new_tag})
        rename_map[old_tag] = new_tag

    changed_novels = _sync_novel_lore_tags(rename_map=rename_map)
    return {
        "ok": True,
        "moved": moved,
        "skipped": skipped,
        "failed": failed,
        "count": len(moved),
        "changed_novels": changed_novels,
    }
