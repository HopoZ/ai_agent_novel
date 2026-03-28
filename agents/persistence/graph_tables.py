from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agents.persistence.storage import get_chapters_dir, list_chapters, load_state, save_chapter, save_state
from agents.state.state_models import ChapterRecord, NovelState


def _novel_dir(novel_id: str) -> Path:
    return Path("storage") / "novels" / novel_id


def _graph_dir(novel_id: str) -> Path:
    return _novel_dir(novel_id) / "graph"


def _character_entities_path(novel_id: str) -> Path:
    return _novel_dir(novel_id) / "character_entities.json"


def _character_relations_path(novel_id: str) -> Path:
    return _novel_dir(novel_id) / "character_relations.json"


def _event_entities_path(novel_id: str) -> Path:
    return _novel_dir(novel_id) / "event_entities.json"


def _event_relations_path(novel_id: str) -> Path:
    return _novel_dir(novel_id) / "event_relations.json"


def ensure_graph_tables(novel_id: str) -> None:
    nd = _novel_dir(novel_id)
    nd.mkdir(parents=True, exist_ok=True)

    # 曾误写入 novel/chapters/{n}.json 的图谱骨架（非 ChapterRecord），直接删除以免干扰加载
    content_chapters = get_chapters_dir(novel_id)
    if content_chapters.exists():
        for fp in content_chapters.glob("*.json"):
            if not fp.stem.isdigit():
                continue
            try:
                raw = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            if "character_ids" not in raw or "who_is_present" in raw:
                continue
            try:
                fp.unlink()
            except Exception:
                pass

    ce_path = _character_entities_path(novel_id)
    cpath = _character_relations_path(novel_id)
    ee_path = _event_entities_path(novel_id)
    epath = _event_relations_path(novel_id)

    # 兼容迁移：从旧 graph/* 或旧 *table.json 自动迁移到新四表路径
    old_cpath = _graph_dir(novel_id) / "character_relations.json"
    old_epath = _graph_dir(novel_id) / "event_relations.json"
    old_character_table = _novel_dir(novel_id) / "character_table.json"
    old_event_table = _novel_dir(novel_id) / "event_table.json"

    if (not cpath.exists()) and old_cpath.exists():
        cpath.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_cpath, cpath)
    if (not epath.exists()) and old_epath.exists():
        epath.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_epath, epath)
    if old_character_table.exists():
        try:
            data = json.loads(old_character_table.read_text(encoding="utf-8"))
            if (not ce_path.exists()) and isinstance(data.get("characters"), list):
                ce_path.write_text(
                    json.dumps({"characters": data.get("characters") or [], "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            if (not cpath.exists()) and isinstance(data.get("relations"), list):
                cpath.write_text(
                    json.dumps({"relations": data.get("relations") or [], "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except Exception:
            pass
    if old_event_table.exists():
        try:
            data = json.loads(old_event_table.read_text(encoding="utf-8"))
            if (not ee_path.exists()) and isinstance(data.get("events"), list):
                ee_path.write_text(
                    json.dumps({"events": data.get("events") or [], "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            if (not epath.exists()) and isinstance(data.get("relations"), list):
                epath.write_text(
                    json.dumps({"relations": data.get("relations") or [], "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except Exception:
            pass

    if ce_path.exists() and cpath.exists() and ee_path.exists() and epath.exists():
        return

    state = load_state(novel_id)
    if not state:
        if not ce_path.exists():
            ce_path.write_text(json.dumps({"characters": [], "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
        if not cpath.exists():
            cpath.write_text(json.dumps({"relations": [], "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
        if not ee_path.exists():
            ee_path.write_text(json.dumps({"events": [], "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
        if not epath.exists():
            epath.write_text(json.dumps({"relations": [], "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    char_entities: List[Dict[str, Any]] = []
    char_relations: List[Dict[str, Any]] = []
    for c in state.characters or []:
        char_entities.append(
            {
                "character_id": c.character_id,
                "description": c.description,
                "current_location": c.current_location,
                "alive": c.alive,
                "goals": list(c.goals or []),
                "known_facts": list(c.known_facts or []),
            }
        )
        src = f"char:{c.character_id}"
        for other, rel in (c.relationships or {}).items():
            if not other:
                continue
            char_relations.append(
                {
                    "source": src,
                    "target": f"char:{other}",
                    "label": str(rel or ""),
                    "kind": "relationship",
                }
            )

    event_rows: List[Dict[str, Any]] = []
    event_relations: List[Dict[str, Any]] = []
    timeline = list(state.world.timeline or [])
    for idx, ev in enumerate(timeline):
        event_rows.append(
            {
                "event_id": f"ev:timeline:{idx}",
                "time_slot": str(ev.time_slot or "").strip(),
                "summary": str(ev.summary or "").strip(),
                "chapter_index": ev.chapter_index,
            }
        )
    for idx in range(0, max(0, len(timeline) - 1)):
        event_relations.append(
            {
                "source": f"ev:timeline:{idx}",
                "target": f"ev:timeline:{idx+1}",
                "label": "时间推进",
                "kind": "timeline_next",
            }
        )

    for chap in list_chapters(novel_id):
        cid = f"ev:chapter:{chap.chapter_index}"
        for p in chap.who_is_present or []:
            ch = f"char:{p.character_id}"
            event_relations.append(
                {
                    "source": ch,
                    "target": cid,
                    "label": p.role_in_scene or "出场",
                    "kind": "appear",
                }
            )

    ce_path.write_text(
        json.dumps({"characters": char_entities, "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    cpath.write_text(
        json.dumps({"relations": char_relations, "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ee_path.write_text(
        json.dumps({"events": event_rows, "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    epath.write_text(
        json.dumps({"relations": event_relations, "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_character_relations(novel_id: str) -> List[Dict[str, Any]]:
    ensure_graph_tables(novel_id)
    p = _character_relations_path(novel_id)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("relations") or []


def load_character_entities(novel_id: str) -> List[Dict[str, Any]]:
    ensure_graph_tables(novel_id)
    p = _character_entities_path(novel_id)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("characters") or []


def save_character_entities(novel_id: str, rows: List[Dict[str, Any]]) -> None:
    ensure_graph_tables(novel_id)
    p = _character_entities_path(novel_id)
    p.write_text(
        json.dumps({"characters": rows, "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_character_relations(novel_id: str, rows: List[Dict[str, Any]]) -> None:
    ensure_graph_tables(novel_id)
    p = _character_relations_path(novel_id)
    p.write_text(
        json.dumps({"relations": rows, "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_event_relations(novel_id: str) -> List[Dict[str, Any]]:
    ensure_graph_tables(novel_id)
    p = _event_relations_path(novel_id)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("relations") or []


def load_event_rows(novel_id: str) -> List[Dict[str, Any]]:
    ensure_graph_tables(novel_id)
    p = _event_entities_path(novel_id)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("events") or []


def save_event_rows(novel_id: str, rows: List[Dict[str, Any]]) -> None:
    ensure_graph_tables(novel_id)
    p = _event_entities_path(novel_id)
    p.write_text(
        json.dumps({"events": rows, "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_event_relations(novel_id: str, rows: List[Dict[str, Any]]) -> None:
    ensure_graph_tables(novel_id)
    p = _event_relations_path(novel_id)
    p.write_text(
        json.dumps({"relations": rows, "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def sync_timeline_event_entity_rows(novel_id: str, state: NovelState) -> None:
    """事件实体表与 state.world.timeline 下标对齐。"""
    ensure_graph_tables(novel_id)
    save_event_rows(
        novel_id,
        [
            {
                "event_id": f"ev:timeline:{i}",
                "time_slot": str(ev.time_slot or "").strip(),
                "summary": str(ev.summary or "").strip(),
                "chapter_index": ev.chapter_index,
            }
            for i, ev in enumerate(state.world.timeline or [])
        ],
    )


def remap_timeline_numeric_edges_after_delete(rows: List[Dict[str, Any]], deleted_idx: int) -> List[Dict[str, Any]]:
    """
    删除 timeline[deleted_idx] 后重写事件关系表中 ev:timeline:{n}：
    n == deleted_idx 的端点所在行删除；n > deleted_idx 变为 n-1；草稿 id（非纯数字）不变。
    """

    def map_node(nid: str) -> Optional[str]:
        if not nid.startswith("ev:timeline:"):
            return nid
        rest = nid.split("ev:timeline:", 1)[1].strip()
        if not rest.isdigit():
            return nid
        n = int(rest)
        if n == deleted_idx:
            return None
        if n > deleted_idx:
            return f"ev:timeline:{n - 1}"
        return nid

    out: List[Dict[str, Any]] = []
    for r in rows:
        src = str(r.get("source", "") or "").strip()
        tgt = str(r.get("target", "") or "").strip()
        ns = map_node(src) if src.startswith("ev:timeline:") else src
        nt = map_node(tgt) if tgt.startswith("ev:timeline:") else tgt
        if ns is None or nt is None:
            continue
        out.append({**r, "source": ns, "target": nt})
    return out


def parse_timeline_index_from_event_id(event_id: str) -> Optional[int]:
    """解析 ev:timeline:{int}；草稿 id（非纯数字后缀）返回 None。"""
    raw = str(event_id or "").strip()
    if not raw.startswith("ev:timeline:"):
        return None
    rest = raw.split("ev:timeline:", 1)[1].strip()
    try:
        return int(rest)
    except ValueError:
        return None


def timeline_next_graph_neighbors(novel_id: str, focus_event_id: str) -> Tuple[List[str], List[str]]:
    """
    基于 event_relations 中 kind=timeline_next 的边：
    - 前置：target == focus 的 source（合法 ev:timeline 索引节点）
    - 后置：source == focus 的 target（合法 ev:timeline 索引节点）
    保持首次遍历顺序，不去重跨类重复（同一 id 只出现一次于各自列表内）。
    """
    focus = str(focus_event_id or "").strip()
    preds: List[str] = []
    succs: List[str] = []
    seen_p: set[str] = set()
    seen_s: set[str] = set()
    for r in load_event_relations(novel_id):
        if str(r.get("kind", "")).strip().lower() != "timeline_next":
            continue
        src = str(r.get("source", "")).strip()
        tgt = str(r.get("target", "")).strip()
        if src == focus and tgt:
            if parse_timeline_index_from_event_id(tgt) is not None and tgt not in seen_s:
                seen_s.add(tgt)
                succs.append(tgt)
        if tgt == focus and src:
            if parse_timeline_index_from_event_id(src) is not None and src not in seen_p:
                seen_p.add(src)
                preds.append(src)
    return preds, succs


def resolve_chapter_event_ids(state: NovelState, chapter_index: int, time_slot: str) -> List[str]:
    """
    章节归属事件：
    1) 优先匹配 timeline.chapter_index == chapter_index
    2) 次优匹配 timeline.time_slot == chapter.time_slot
    3) 无匹配则返回空（由上层决定是否兜底）
    """
    timeline = list(state.world.timeline or [])
    by_index: List[str] = []
    for i, ev in enumerate(timeline):
        if ev.chapter_index == chapter_index:
            by_index.append(f"ev:timeline:{i}")
    if by_index:
        return by_index

    ts = str(time_slot or "").strip()
    if ts:
        by_slot = [f"ev:timeline:{i}" for i, ev in enumerate(timeline) if str(ev.time_slot or "").strip() == ts]
        if by_slot:
            return by_slot
    return []


def replace_appear_edges_for_chapter(novel_id: str, chapter: ChapterRecord) -> None:
    rows = load_event_relations(novel_id)
    target = f"ev:chapter:{chapter.chapter_index}"
    rows = [
        r for r in rows
        if not (
            str(r.get("kind", "")).strip().lower() == "appear"
            and str(r.get("target", "")) == target
        )
    ]
    for p in chapter.who_is_present or []:
        rows.append(
            {
                "source": f"char:{p.character_id}",
                "target": target,
                "label": p.role_in_scene or "出场",
                "kind": "appear",
            }
        )
    save_event_relations(novel_id, rows)


def replace_timeline_next_edges_from_state(novel_id: str, state: NovelState) -> None:
    """
    根据 state.world.timeline 同步 timeline_next 事件关系边：
    - 保留已有手工边（含空 target 的“待定”草稿）
    - 仅为缺失下跳的节点补默认顺序边 i -> i+1
    - 清理越界 source/target（timeline 缩短后的脏边）
    """
    rows = load_event_relations(novel_id)
    timeline = list(state.world.timeline or [])
    timeline_len = len(timeline)

    def _timeline_idx(node_id: str) -> Optional[int]:
        raw = str(node_id or "").strip()
        if not raw.startswith("ev:timeline:"):
            return None
        try:
            return int(raw.split("ev:timeline:", 1)[1].strip())
        except Exception:
            return None

    kept_timeline_rows: List[Dict[str, Any]] = []
    other_rows: List[Dict[str, Any]] = []
    used_sources: set[str] = set()

    for r in rows:
        if str(r.get("kind", "")).strip().lower() != "timeline_next":
            other_rows.append(r)
            continue

        src = str(r.get("source", "")).strip()
        tgt = str(r.get("target", "")).strip()
        src_idx = _timeline_idx(src)
        tgt_idx = _timeline_idx(tgt) if tgt else None

        # source 必须是有效 timeline 节点；无 source 的草稿不保留
        if src_idx is None or not (0 <= src_idx < timeline_len):
            continue

        # 空 target 视为“待定”草稿，保留
        if tgt == "":
            if src in used_sources:
                continue
            used_sources.add(src)
            kept_timeline_rows.append(
                {
                    "source": src,
                    "target": "",
                    "label": (str(r.get("label", "")).strip() or "待完善"),
                    "kind": "timeline_next",
                }
            )
            continue

        # 非空 target 必须有效
        if tgt_idx is None or not (0 <= tgt_idx < timeline_len):
            continue
        if src in used_sources:
            continue
        used_sources.add(src)
        kept_timeline_rows.append(
            {
                "source": src,
                "target": tgt,
                "label": (str(r.get("label", "")).strip() or "时间推进"),
                "kind": "timeline_next",
            }
        )

    # 为没有下跳定义的节点补默认顺序边
    for idx in range(0, max(0, timeline_len - 1)):
        src = f"ev:timeline:{idx}"
        if src in used_sources:
            continue
        kept_timeline_rows.append(
            {
                "source": src,
                "target": f"ev:timeline:{idx+1}",
                "label": "时间推进",
                "kind": "timeline_next",
            }
        )

    rows = other_rows + kept_timeline_rows
    save_event_relations(novel_id, rows)


def persist_chapter_artifacts(
    novel_id: str,
    chapter: ChapterRecord,
    next_state: NovelState,
    chapter_preset_name: Optional[str] = None,
) -> None:
    """
    正文 API 的统一落盘入口：
    1) 保存章节
    2) 保存 next_state（state.json 不含 relationships 真源）
    3) 同步四表侧：人物/事件实体行、appear 边、timeline_next 边
    """
    save_chapter(novel_id, chapter, chapter_preset_name=chapter_preset_name)

    next_state.meta.current_chapter_index = chapter.chapter_index
    next_state.meta.updated_at = datetime.utcnow()
    save_state(novel_id, next_state)

    ensure_graph_tables(novel_id)
    # 同步实体表（人物/事件）
    save_character_entities(
        novel_id,
        [
            {
                "character_id": c.character_id,
                "description": c.description,
                "current_location": c.current_location,
                "alive": c.alive,
                "goals": list(c.goals or []),
                "known_facts": list(c.known_facts or []),
            }
            for c in (next_state.characters or [])
        ],
    )
    save_event_rows(
        novel_id,
        [
            {
                "event_id": f"ev:timeline:{i}",
                "time_slot": str(ev.time_slot or "").strip(),
                "summary": str(ev.summary or "").strip(),
                "chapter_index": ev.chapter_index,
            }
            for i, ev in enumerate(next_state.world.timeline or [])
        ],
    )
    replace_appear_edges_for_chapter(novel_id, chapter)
    replace_timeline_next_edges_from_state(novel_id, next_state)


def hydrate_state_character_relationships(novel_id: str, state: NovelState) -> NovelState:
    """
    将 state.characters[*].relationships 由 character_relations 表实时回填。
    该函数不落盘，只用于运行期读取，确保人物关系以 character_relations 为真源。
    """
    rows = load_character_relations(novel_id)
    rel_map: Dict[str, Dict[str, str]] = {}
    for r in rows:
        if str(r.get("kind", "")).strip().lower() != "relationship":
            continue
        src = str(r.get("source", "")).strip()
        tgt = str(r.get("target", "")).strip()
        label = str(r.get("label", "")).strip()
        if (not src.startswith("char:")) or (not tgt.startswith("char:")):
            continue
        src_id = src.split("char:", 1)[1].strip()
        tgt_id = tgt.split("char:", 1)[1].strip()
        if not src_id or not tgt_id:
            continue
        rel_map.setdefault(src_id, {})[tgt_id] = label

    for c in state.characters or []:
        c.relationships = rel_map.get(c.character_id, {})
    return state


def split_relations(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rel = []
    other = []
    for r in rows:
        kind = str(r.get("kind", "")).strip().lower()
        if kind == "relationship":
            rel.append(r)
        else:
            other.append(r)
    return rel, other

