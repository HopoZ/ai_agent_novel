"""
单本小说 SQLite 存储（`storage/novels/<novel_id>/novel.db`）。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from agents.persistence.env_paths import get_storage_root
from agents.state.state_models import ChapterRecord

SCHEMA_VERSION = 1


def _novel_dir(novel_id: str) -> Path:
    UUID(novel_id)
    return get_storage_root() / "novels" / novel_id


def get_db_path(novel_id: str) -> Path:
    return _novel_dir(novel_id) / "novel.db"


def db_exists(novel_id: str) -> bool:
    return get_db_path(novel_id).exists()


def _is_graph_chapter_table_stub(data: object) -> bool:
    if not isinstance(data, dict):
        return False
    if "character_ids" not in data:
        return False
    if "who_is_present" in data:
        return False
    return True


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS novel_state (
            novel_id TEXT PRIMARY KEY,
            json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_index INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chapters_chapter_index ON chapters(chapter_index);
        CREATE TABLE IF NOT EXISTS character_entities (
            character_id TEXT PRIMARY KEY,
            description TEXT,
            goals_json TEXT NOT NULL DEFAULT '[]',
            known_facts_json TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS character_relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            label TEXT,
            kind TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS event_entities (
            event_id TEXT PRIMARY KEY,
            time_slot TEXT,
            summary TEXT
        );
        CREATE TABLE IF NOT EXISTS event_relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            label TEXT,
            kind TEXT NOT NULL
        );
        """
    )
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )


@contextmanager
def sqlite_connection(novel_id: str):
    path = get_db_path(novel_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _ensure_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _meta_get(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return str(row["value"]) if row else None


def _meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (key, value))


def is_graph_initialized(novel_id: str) -> bool:
    if not db_exists(novel_id):
        return False
    with sqlite_connection(novel_id) as conn:
        return _meta_get(conn, "graph_initialized") == "1"


def set_graph_initialized(novel_id: str) -> None:
    with sqlite_connection(novel_id) as conn:
        _meta_set(conn, "graph_initialized", "1")


def read_state_json(novel_id: str) -> Optional[str]:
    with sqlite_connection(novel_id) as conn:
        row = conn.execute("SELECT json FROM novel_state WHERE novel_id=?", (novel_id,)).fetchone()
        return str(row["json"]) if row else None


def write_state_json(novel_id: str, json_str: str) -> None:
    with sqlite_connection(novel_id) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO novel_state(novel_id, json) VALUES(?, ?)",
            (novel_id, json_str),
        )


def delete_all_chapters(novel_id: str) -> None:
    with sqlite_connection(novel_id) as conn:
        conn.execute("DELETE FROM chapters")


def insert_chapter_row(novel_id: str, chapter: ChapterRecord) -> None:
    payload = chapter.model_dump_json(ensure_ascii=False)
    created = chapter.created_at.isoformat() if chapter.created_at else datetime.now(UTC).isoformat()
    with sqlite_connection(novel_id) as conn:
        conn.execute(
            "INSERT INTO chapters(chapter_index, created_at, json) VALUES(?,?,?)",
            (chapter.chapter_index, created, payload),
        )


def load_all_chapter_records(novel_id: str) -> List[ChapterRecord]:
    with sqlite_connection(novel_id) as conn:
        rows = conn.execute(
            "SELECT json FROM chapters ORDER BY chapter_index ASC, created_at ASC"
        ).fetchall()
    out: List[ChapterRecord] = []
    for r in rows:
        try:
            data = json.loads(r["json"])
            if _is_graph_chapter_table_stub(data):
                continue
            out.append(ChapterRecord.model_validate(data))
        except Exception:
            continue
    return out


def replace_character_entities(novel_id: str, rows: List[Dict[str, Any]]) -> None:
    with sqlite_connection(novel_id) as conn:
        conn.execute("DELETE FROM character_entities")
        for row in rows:
            cid = str(row.get("character_id", "") or "")
            if not cid:
                continue
            conn.execute(
                """INSERT INTO character_entities(character_id, description, goals_json, known_facts_json)
                   VALUES(?,?,?,?)""",
                (
                    cid,
                    row.get("description"),
                    json.dumps(row.get("goals") or [], ensure_ascii=False),
                    json.dumps(row.get("known_facts") or [], ensure_ascii=False),
                ),
            )


def load_character_entities_rows(novel_id: str) -> List[Dict[str, Any]]:
    with sqlite_connection(novel_id) as conn:
        cur = conn.execute(
            "SELECT character_id, description, goals_json, known_facts_json FROM character_entities ORDER BY character_id"
        )
        out: List[Dict[str, Any]] = []
        for r in cur.fetchall():
            try:
                goals = json.loads(r["goals_json"] or "[]")
                facts = json.loads(r["known_facts_json"] or "[]")
            except Exception:
                goals, facts = [], []
            out.append(
                {
                    "character_id": r["character_id"],
                    "description": r["description"],
                    "goals": goals,
                    "known_facts": facts,
                }
            )
        return out


def replace_character_relations(novel_id: str, rows: List[Dict[str, Any]]) -> None:
    with sqlite_connection(novel_id) as conn:
        conn.execute("DELETE FROM character_relations")
        for r in rows:
            conn.execute(
                "INSERT INTO character_relations(source, target, label, kind) VALUES(?,?,?,?)",
                (
                    str(r.get("source", "") or ""),
                    str(r.get("target", "") or ""),
                    str(r.get("label", "") or ""),
                    str(r.get("kind", "") or ""),
                ),
            )


def load_character_relations_rows(novel_id: str) -> List[Dict[str, Any]]:
    with sqlite_connection(novel_id) as conn:
        cur = conn.execute(
            "SELECT source, target, label, kind FROM character_relations ORDER BY id ASC"
        )
        return [
            {
                "source": r["source"],
                "target": r["target"],
                "label": r["label"],
                "kind": r["kind"],
            }
            for r in cur.fetchall()
        ]


def replace_event_entities(novel_id: str, rows: List[Dict[str, Any]]) -> None:
    with sqlite_connection(novel_id) as conn:
        conn.execute("DELETE FROM event_entities")
        for row in rows:
            eid = str(row.get("event_id", "") or "")
            if not eid:
                continue
            conn.execute(
                "INSERT INTO event_entities(event_id, time_slot, summary) VALUES(?,?,?)",
                (eid, str(row.get("time_slot", "") or ""), str(row.get("summary", "") or "")),
            )


def load_event_entities_rows(novel_id: str) -> List[Dict[str, Any]]:
    with sqlite_connection(novel_id) as conn:
        cur = conn.execute("SELECT event_id, time_slot, summary FROM event_entities ORDER BY event_id")
        return [
            {"event_id": r["event_id"], "time_slot": r["time_slot"] or "", "summary": r["summary"] or ""}
            for r in cur.fetchall()
        ]


def replace_event_relations(novel_id: str, rows: List[Dict[str, Any]]) -> None:
    with sqlite_connection(novel_id) as conn:
        conn.execute("DELETE FROM event_relations")
        for r in rows:
            conn.execute(
                "INSERT INTO event_relations(source, target, label, kind) VALUES(?,?,?,?)",
                (
                    str(r.get("source", "") or ""),
                    str(r.get("target", "") or ""),
                    str(r.get("label", "") or ""),
                    str(r.get("kind", "") or ""),
                ),
            )


def load_event_relations_rows(novel_id: str) -> List[Dict[str, Any]]:
    with sqlite_connection(novel_id) as conn:
        cur = conn.execute("SELECT source, target, label, kind FROM event_relations ORDER BY id ASC")
        return [
            {
                "source": r["source"],
                "target": r["target"],
                "label": r["label"],
                "kind": r["kind"],
            }
            for r in cur.fetchall()
        ]
