from __future__ import annotations

from typing import List, Optional

AUTO_LORE_PREFIX = "自动生成/"


def norm_tag(tag: str) -> str:
    return str(tag or "").replace("\\", "/").strip().strip("/")


def is_auto_lore_tag(tag: str) -> bool:
    return norm_tag(tag).startswith(AUTO_LORE_PREFIX)


def is_auto_lore_tag_for_novel(tag: str, novel_id: str) -> bool:
    prefix = f"{AUTO_LORE_PREFIX}{novel_id}/"
    return norm_tag(tag).startswith(prefix)


def normalize_novel_lore_tags(
    *,
    novel_id: str,
    tags: List[str],
    ensure_auto_tags: Optional[List[str]] = None,
) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in (tags or []):
        s = norm_tag(raw)
        if not s or s in seen:
            continue
        if is_auto_lore_tag(s) and (not is_auto_lore_tag_for_novel(s, novel_id)):
            continue
        seen.add(s)
        out.append(s)
    for raw in (ensure_auto_tags or []):
        s = norm_tag(raw)
        if not s or s in seen:
            continue
        if not is_auto_lore_tag_for_novel(s, novel_id):
            continue
        seen.add(s)
        out.append(s)
    return out

