from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from agents.state.state_models import ChapterRecord, ContinuityState, NovelMeta, NovelState, WorldState


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


def _is_graph_chapter_table_stub(data: object) -> bool:
    """图谱章节表骨架（误入 chapters/ 目录时勿当 ChapterRecord 解析）。"""
    if not isinstance(data, dict):
        return False
    if "character_ids" not in data:
        return False
    if "who_is_present" in data:
        return False
    return True


def load_state(novel_id: str) -> Optional[NovelState]:
    p = get_state_path(novel_id)
    state: Optional[NovelState] = None
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        state = NovelState.model_validate(data)

    # 每次 load 都按最新章节“重算运行态关键字段”，避免一直沿用旧 state 快照。
    chapters = list_chapters(novel_id)
    if not chapters:
        return state

    latest = max(chapters, key=lambda c: (c.chapter_index, c.created_at))
    if state is None:
        state = NovelState(
            meta=NovelMeta(
                novel_id=novel_id,
                novel_title="未命名小说",
                initialized=False,
                current_chapter_index=int(latest.chapter_index),
            ),
            continuity=ContinuityState(
                time_slot=str(latest.time_slot or "未设置"),
                pov_character_id=latest.pov_character_id,
                who_is_present=(latest.who_is_present or []),
            ),
            characters=[],
            world=WorldState(),
            recent_summaries=[],
        )
    else:
        state.meta.current_chapter_index = int(latest.chapter_index)
        state.continuity.time_slot = str(latest.time_slot or state.continuity.time_slot or "未设置")
        state.continuity.pov_character_id = latest.pov_character_id or state.continuity.pov_character_id
        state.continuity.who_is_present = latest.who_is_present or []

    # 回写一次，让 state.json 始终是“本次加载后”的最新运行态。
    try:
        save_state(novel_id, state)
    except Exception:
        pass
    return state


def save_state(novel_id: str, state: NovelState) -> None:
    ensure_novel_dirs(novel_id)
    p = get_state_path(novel_id)
    # 人物关系（relationships）已迁移到 graph/character_relations.json，state.json 不再作为真源。
    # 这里强制清空，避免旧数据回流/双写不一致。
    state_to_save = state.model_copy(deep=True)
    for c in state_to_save.characters or []:
        c.relationships = {}
    p.write_text(state_to_save.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")


def load_chapter(novel_id: str, chapter_index: int) -> Optional[ChapterRecord]:
    def _scan_dir() -> Optional[ChapterRecord]:
        for fp in get_chapters_dir(novel_id).glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                if _is_graph_chapter_table_stub(data):
                    continue
                rec = ChapterRecord.model_validate(data)
            except Exception:
                continue
            if rec.chapter_index == chapter_index:
                return rec
        return None

    p = get_chapter_path(novel_id, chapter_index)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not _is_graph_chapter_table_stub(data):
                return ChapterRecord.model_validate(data)
        except Exception:
            pass
        return _scan_dir()
    return _scan_dir()


def list_chapters(novel_id: str) -> List[ChapterRecord]:
    out: List[ChapterRecord] = []
    chapters_dir = get_chapters_dir(novel_id)
    if not chapters_dir.exists():
        return out
    for fp in chapters_dir.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if _is_graph_chapter_table_stub(data):
                continue
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

