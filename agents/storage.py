from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from .state_models import ChapterRecord, NovelState


APP_STORAGE_DIR = Path("storage")
_INVALID_FILENAME_CHARS_RE = re.compile(r'[\\/:*?"<>|]+')


def _safe_stem(name: str, fallback: str = "chapter") -> str:
    text = (name or "").strip()
    if not text:
        return fallback
    text = _INVALID_FILENAME_CHARS_RE.sub("_", text)
    text = re.sub(r"\s+", "_", text).strip("._")
    return (text or fallback)[:80]


def _novel_dir(novel_id: str) -> Path:
    # novel_id 由 uuid 生成，做一个基本校验，避免奇怪路径
    UUID(novel_id)
    return APP_STORAGE_DIR / "novels" / novel_id


def get_state_path(novel_id: str) -> Path:
    return _novel_dir(novel_id) / "state.json"


def get_chapters_dir(novel_id: str) -> Path:
    return _novel_dir(novel_id) / "chapters"


def get_chapter_path(novel_id: str, chapter_index: int) -> Path:
    return get_chapters_dir(novel_id) / f"{chapter_index}.json"


def ensure_novel_dirs(novel_id: str) -> None:
    d = _novel_dir(novel_id)
    d.mkdir(parents=True, exist_ok=True)
    get_chapters_dir(novel_id).mkdir(parents=True, exist_ok=True)


def load_state(novel_id: str) -> Optional[NovelState]:
    p = get_state_path(novel_id)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return NovelState.model_validate(data)


def save_state(novel_id: str, state: NovelState) -> None:
    ensure_novel_dirs(novel_id)
    p = get_state_path(novel_id)
    p.write_text(state.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")


def load_chapter(novel_id: str, chapter_index: int) -> Optional[ChapterRecord]:
    p = get_chapter_path(novel_id, chapter_index)
    if not p.exists():
        # 兼容新文件命名：扫描 chapters 下任意文件，按 chapter_index 匹配
        for fp in get_chapters_dir(novel_id).glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                rec = ChapterRecord.model_validate(data)
            except Exception:
                continue
            if rec.chapter_index == chapter_index:
                return rec
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return ChapterRecord.model_validate(data)


def list_chapters(novel_id: str) -> List[ChapterRecord]:
    out: List[ChapterRecord] = []
    chapters_dir = get_chapters_dir(novel_id)
    if not chapters_dir.exists():
        return out
    for fp in chapters_dir.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            out.append(ChapterRecord.model_validate(data))
        except Exception:
            continue
    # 先按 chapter_index，再按 created_at 排序
    out.sort(key=lambda c: (c.chapter_index, c.created_at))
    return out


def save_chapter(novel_id: str, chapter: ChapterRecord, chapter_preset_name: Optional[str] = None) -> Path:
    ensure_novel_dirs(novel_id)
    preset = (chapter_preset_name or chapter.chapter_preset_name or "").strip()
    if preset:
        chapter.chapter_preset_name = preset
        stem = _safe_stem(preset, fallback=f"chapter_{chapter.chapter_index}")
    else:
        stem = f"chapter_{chapter.chapter_index}"
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    p = get_chapters_dir(novel_id) / f"{stem}_{ts}.json"
    p.write_text(chapter.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")
    return p

