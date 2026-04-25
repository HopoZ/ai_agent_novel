from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from agents.persistence.env_paths import get_storage_root
from agents.state.state_models import EventPlan, EventPlanRecord


def _event_plans_dir(novel_id: str) -> Path:
    return get_storage_root() / "novels" / novel_id / "event_plans"


def _event_plan_path(novel_id: str, event_id: str) -> Path:
    safe_event = str(event_id or "").strip().replace("\\", "_").replace("/", "_").replace(":", "_")
    return _event_plans_dir(novel_id) / f"{safe_event}.json"


def save_event_plan(novel_id: str, event_id: str, plan: EventPlan) -> EventPlanRecord:
    p = _event_plan_path(novel_id, event_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    prev = load_event_plan(novel_id, event_id)
    rec = EventPlanRecord(
        event_plan_id=(prev.event_plan_id if prev else f"ep:{uuid4().hex}"),
        novel_id=novel_id,
        event_id=event_id,
        plan=plan,
        created_at=(prev.created_at if prev else now),
        updated_at=now,
    )
    p.write_text(rec.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")
    return rec


def load_event_plan(novel_id: str, event_id: str) -> Optional[EventPlanRecord]:
    p = _event_plan_path(novel_id, event_id)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return EventPlanRecord.model_validate(data)
    except Exception:
        return None


def list_event_plans(novel_id: str) -> List[EventPlanRecord]:
    d = _event_plans_dir(novel_id)
    if not d.exists():
        return []
    out: List[EventPlanRecord] = []
    for fp in d.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            out.append(EventPlanRecord.model_validate(data))
        except Exception:
            continue
    out.sort(key=lambda x: x.updated_at, reverse=True)
    return out


def delete_event_plan(novel_id: str, event_id: str) -> bool:
    p = _event_plan_path(novel_id, event_id)
    if not p.exists():
        return False
    p.unlink()
    return True
