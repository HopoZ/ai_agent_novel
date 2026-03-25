from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from uuid import UUID

from .state_models import ChapterRecord, NovelState


APP_STORAGE_DIR = Path("storage")


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
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return ChapterRecord.model_validate(data)


def save_chapter(novel_id: str, chapter: ChapterRecord) -> None:
    ensure_novel_dirs(novel_id)
    p = get_chapter_path(novel_id, chapter.chapter_index)
    p.write_text(chapter.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")

