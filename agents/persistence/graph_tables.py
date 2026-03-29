from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agents.persistence.storage import (
    get_chapters_dir,
    get_state_path,
    list_chapters,
    list_chapters_latest_per_index,
    load_state,
    save_chapter,
    save_state,
)
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


def new_timeline_event_id() -> str:
    return f"ev:timeline:{uuid.uuid4().hex}"


def validate_timeline_event_id(state: NovelState, eid: Optional[str]) -> Optional[str]:
    """若 eid 为当前 timeline 中存在的稳定 id，则原样返回，否则 None。"""
    x = (eid or "").strip()
    if not x.startswith("ev:timeline:"):
        return None
    for ev in state.world.timeline or []:
        if (ev.event_id or "").strip() == x:
            return x
    return None


def resolve_chapter_timeline_event_id(state: NovelState, chapter: ChapterRecord) -> Optional[str]:
    """
    章 → 归属的时间线事件 id：
    1) ChapterRecord.timeline_event_id 若在 state.timeline 中存在则采用（多章可同指一事件）
    2) 否则按 time_slot 文本对齐 timeline 中第一条匹配
    """
    tid = (chapter.timeline_event_id or "").strip()
    if tid.startswith("ev:timeline:"):
        v = validate_timeline_event_id(state, tid)
        if v:
            return v
    ts = str(chapter.time_slot or "").strip()
    if not ts:
        return None
    for ev in state.world.timeline or []:
        if str(ev.time_slot or "").strip() == ts and (ev.event_id or "").strip():
            return str(ev.event_id).strip()
    return None


def timeline_index_for_node_id(state: NovelState, node_id: Optional[str]) -> Optional[int]:
    """时间线节点 → 列表下标：支持稳定 id（ev:timeline:{hex}）或兼容旧请求的纯数字下标。"""
    nid = (node_id or "").strip()
    if not nid.startswith("ev:timeline:"):
        return None
    rest = nid.split("ev:timeline:", 1)[1].strip()
    tl = list(state.world.timeline or [])
    if rest.isdigit():
        j = int(rest)
        if 0 <= j < len(tl):
            return j
        return None
    for i, ev in enumerate(tl):
        eid = (ev.event_id or "").strip()
        if eid and eid == nid:
            return i
    return None


def ensure_timeline_stable_ids(novel_id: str, state: NovelState) -> None:
    """
    为每条 timeline 分配稳定 event_id，并把 event_relations / event_entities 里
    旧的 ev:timeline:{下标} 端点改写为稳定 id。不调用 ensure_graph_tables，避免与 load_state 递归。
    """
    tl = list(state.world.timeline or [])
    if not tl:
        return

    changed_state = any(not (ev.event_id and str(ev.event_id).strip()) for ev in tl)
    if changed_state:
        for ev in tl:
            if not (ev.event_id and str(ev.event_id).strip()):
                ev.event_id = new_timeline_event_id()

    idx_to_id = {i: (tl[i].event_id or "").strip() for i in range(len(tl))}

    def map_node(nid: str) -> str:
        s = (nid or "").strip()
        if not s.startswith("ev:timeline:"):
            return s
        rest = s.split("ev:timeline:", 1)[1].strip()
        if rest.isdigit():
            j = int(rest)
            if 0 <= j < len(tl) and idx_to_id.get(j):
                return idx_to_id[j]
        return s

    er_path = _event_relations_path(novel_id)
    ee_path = _event_entities_path(novel_id)
    need_remap = changed_state
    rel_rows: Optional[List[Dict[str, Any]]] = None
    er_data: Optional[Dict[str, Any]] = None
    if er_path.exists():
        try:
            er_data = json.loads(er_path.read_text(encoding="utf-8"))
            rel_rows = list(er_data.get("relations") or [])
        except Exception:
            rel_rows = None
    if rel_rows is not None and not need_remap:
        for r in rel_rows:
            for k in ("source", "target"):
                v = str(r.get(k, "") or "").strip()
                if v.startswith("ev:timeline:"):
                    rest = v.split("ev:timeline:", 1)[1].strip()
                    if rest.isdigit():
                        need_remap = True
                        break
            if need_remap:
                break

    wrote = False
    if need_remap and rel_rows is not None and er_data is not None:
        new_rel = []
        for r in rel_rows:
            ns = map_node(str(r.get("source", "") or ""))
            nt = map_node(str(r.get("target", "") or ""))
            new_rel.append({**r, "source": ns, "target": nt})
        er_data["relations"] = new_rel
        er_data["updated_at"] = datetime.utcnow().isoformat()
        er_path.parent.mkdir(parents=True, exist_ok=True)
        er_path.write_text(json.dumps(er_data, ensure_ascii=False, indent=2), encoding="utf-8")
        wrote = True

    if need_remap and ee_path.exists():
        try:
            ee_raw = json.loads(ee_path.read_text(encoding="utf-8"))
            events = list(ee_raw.get("events") or [])
            touched = False
            for row in events:
                old = str(row.get("event_id", "") or "").strip()
                neu = map_node(old)
                if neu != old:
                    row["event_id"] = neu
                    touched = True
            if touched:
                ee_raw["events"] = events
                ee_raw["updated_at"] = datetime.utcnow().isoformat()
                ee_path.write_text(json.dumps(ee_raw, ensure_ascii=False, indent=2), encoding="utf-8")
                wrote = True
        except Exception:
            pass

    if changed_state or wrote:
        save_state(novel_id, state)


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

    sp = get_state_path(novel_id)
    if not sp.exists():
        if not ce_path.exists():
            ce_path.write_text(json.dumps({"characters": [], "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
        if not cpath.exists():
            cpath.write_text(json.dumps({"relations": [], "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
        if not ee_path.exists():
            ee_path.write_text(json.dumps({"events": [], "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
        if not epath.exists():
            epath.write_text(json.dumps({"relations": [], "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    try:
        state = NovelState.model_validate(json.loads(sp.read_text(encoding="utf-8")))
    except Exception:
        if not ce_path.exists():
            ce_path.write_text(json.dumps({"characters": [], "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
        if not cpath.exists():
            cpath.write_text(json.dumps({"relations": [], "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
        if not ee_path.exists():
            ee_path.write_text(json.dumps({"events": [], "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
        if not epath.exists():
            epath.write_text(json.dumps({"relations": [], "updated_at": datetime.utcnow().isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    ensure_timeline_stable_ids(novel_id, state)

    char_entities: List[Dict[str, Any]] = []
    char_relations: List[Dict[str, Any]] = []
    for c in state.characters or []:
        char_entities.append(
            {
                "character_id": c.character_id,
                "description": c.description,
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
    for ev in timeline:
        eid = (ev.event_id or "").strip() or new_timeline_event_id()
        if not (ev.event_id and str(ev.event_id).strip()):
            ev.event_id = eid
        event_rows.append(
            {
                "event_id": eid,
                "time_slot": str(ev.time_slot or "").strip(),
                "summary": str(ev.summary or "").strip(),
            }
        )
    for idx in range(0, max(0, len(timeline) - 1)):
        a = (timeline[idx].event_id or "").strip()
        b = (timeline[idx + 1].event_id or "").strip()
        if not a or not b:
            continue
        event_relations.append(
            {
                "source": a,
                "target": b,
                "label": "时间推进",
                "kind": "timeline_next",
            }
        )

    for chap in list_chapters_latest_per_index(novel_id):
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
        teid = resolve_chapter_timeline_event_id(state, chap)
        if teid:
            event_relations.append(
                {
                    "source": cid,
                    "target": teid,
                    "label": "属于事件",
                    "kind": "chapter_belongs",
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
    save_state(novel_id, state)


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
    """事件实体表与 state.world.timeline 对齐（每行 event_id 为稳定 id）。"""
    ensure_graph_tables(novel_id)
    ensure_timeline_stable_ids(novel_id, state)
    save_event_rows(
        novel_id,
        [
            {
                "event_id": (ev.event_id or ""),
                "time_slot": str(ev.time_slot or "").strip(),
                "summary": str(ev.summary or "").strip(),
            }
            for ev in (state.world.timeline or [])
        ],
    )


def timeline_next_graph_neighbors(novel_id: str, focus_event_id: str) -> Tuple[List[str], List[str]]:
    """
    基于 event_relations 中 kind=timeline_next 的边：
    端点为稳定 ev:timeline:{hex}（或兼容旧数据中带纯数字下标的 id）。
    """
    st = load_state(novel_id)
    tl_ids: set[str] = set()
    if st:
        for ev in st.world.timeline or []:
            eid = (ev.event_id or "").strip()
            if eid:
                tl_ids.add(eid)
    focus = str(focus_event_id or "").strip()
    preds: List[str] = []
    succs: List[str] = []
    seen_p: set[str] = set()
    seen_s: set[str] = set()

    def _is_timeline_node(nid: str) -> bool:
        if not nid.startswith("ev:timeline:"):
            return False
        rest = nid.split("ev:timeline:", 1)[1].strip()
        if rest.isdigit():
            return True
        return nid in tl_ids

    for r in load_event_relations(novel_id):
        if str(r.get("kind", "")).strip().lower() != "timeline_next":
            continue
        src = str(r.get("source", "")).strip()
        tgt = str(r.get("target", "")).strip()
        if src == focus and tgt:
            if _is_timeline_node(tgt) and tgt not in seen_s:
                seen_s.add(tgt)
                succs.append(tgt)
        if tgt == focus and src:
            if _is_timeline_node(src) and src not in seen_p:
                seen_p.add(src)
                preds.append(src)
    return preds, succs


def resolve_chapter_event_ids(state: NovelState, time_slot: str) -> List[str]:
    """按 time_slot 文本列出所有匹配的时间线事件 id（弱对齐；显式归属见 ChapterRecord.timeline_event_id）。"""
    ts = str(time_slot or "").strip()
    if not ts:
        return []
    timeline = list(state.world.timeline or [])
    return [
        str(ev.event_id).strip()
        for ev in timeline
        if str(ev.time_slot or "").strip() == ts and (ev.event_id or "").strip()
    ]


def replace_chapter_belongs_for_chapter(novel_id: str, state: NovelState, chapter: ChapterRecord) -> None:
    """重写本章的 chapter_belongs 边，与 ChapterRecord + state 一致。"""
    rows = load_event_relations(novel_id)
    target = f"ev:chapter:{chapter.chapter_index}"
    rows = [
        r
        for r in rows
        if not (
            str(r.get("kind", "")).strip().lower() == "chapter_belongs"
            and str(r.get("source", "")).strip() == target
        )
    ]
    teid = resolve_chapter_timeline_event_id(state, chapter)
    if teid:
        rows.append(
            {
                "source": target,
                "target": teid,
                "label": "属于事件",
                "kind": "chapter_belongs",
            }
        )
    save_event_relations(novel_id, rows)


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
    - 仅为缺失下跳的节点补默认顺序边（按列表顺序，稳定 id 端点）
    - 清理指向已不存在 timeline 节点的边
    """
    ensure_timeline_stable_ids(novel_id, state)
    rows = load_event_relations(novel_id)
    timeline = list(state.world.timeline or [])
    timeline_len = len(timeline)
    valid: set[str] = {(ev.event_id or "").strip() for ev in timeline if (ev.event_id or "").strip()}

    kept_timeline_rows: List[Dict[str, Any]] = []
    other_rows: List[Dict[str, Any]] = []
    used_sources: set[str] = set()

    for r in rows:
        if str(r.get("kind", "")).strip().lower() != "timeline_next":
            other_rows.append(r)
            continue

        src = str(r.get("source", "")).strip()
        tgt = str(r.get("target", "")).strip()

        if src not in valid:
            continue

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

        if tgt not in valid:
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

    for idx in range(0, max(0, timeline_len - 1)):
        a = (timeline[idx].event_id or "").strip()
        b = (timeline[idx + 1].event_id or "").strip()
        if not a or not b:
            continue
        if a in used_sources:
            continue
        kept_timeline_rows.append(
            {
                "source": a,
                "target": b,
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
                "goals": list(c.goals or []),
                "known_facts": list(c.known_facts or []),
            }
            for c in (next_state.characters or [])
        ],
    )
    ensure_timeline_stable_ids(novel_id, next_state)
    save_event_rows(
        novel_id,
        [
            {
                "event_id": (ev.event_id or ""),
                "time_slot": str(ev.time_slot or "").strip(),
                "summary": str(ev.summary or "").strip(),
            }
            for ev in (next_state.world.timeline or [])
        ],
    )
    replace_appear_edges_for_chapter(novel_id, chapter)
    replace_chapter_belongs_for_chapter(novel_id, next_state, chapter)
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

