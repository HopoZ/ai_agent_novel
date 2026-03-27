from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .loader import LoreLoader


SUMMARY_DIR = Path("storage") / "lore_summaries"


def _summary_id(tags: List[str], source_hash: str, mode: str) -> str:
    raw = json.dumps(
        {"tags": tags, "source_hash": source_hash, "mode": mode},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_source_map(loader: LoreLoader, tags: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for tag in tags:
        out[tag] = loader.get_markdown_by_tag(tag) or ""
    return out


def source_hash_from_map(source: Dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(source, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def load_cached_summary(tags: List[str], source_hash: str, mode: str) -> Optional[Dict[str, object]]:
    sid = _summary_id(tags, source_hash, mode=mode)
    path = SUMMARY_DIR / f"{sid}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    data["cached"] = True
    return data


def save_summary(
    tags: List[str],
    source_hash: str,
    summary_text: str,
    mode: str,
    tag_summaries: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    sid = _summary_id(tags, source_hash, mode=mode)
    path = SUMMARY_DIR / f"{sid}.json"
    data = {
        "summary_id": sid,
        "tags": tags,
        "source_hash": source_hash,
        "summary_text": summary_text,
        "tag_summaries": tag_summaries or [],
        "mode": mode,
        "cached": False,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def get_lore_summary(summary_id: str) -> Optional[Dict[str, object]]:
    sid = (summary_id or "").strip()
    if not sid:
        return None
    path = SUMMARY_DIR / f"{sid}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
