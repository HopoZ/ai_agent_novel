from __future__ import annotations

from typing import Any, Dict, List, Tuple

from agents.persistence.event_plan_store import load_event_plan
from agents.persistence.storage import load_state
from agents.state.state_models import Beat, ChapterPlan, CharacterPresence
from webapp.backend.schemas import RunModeRequest


def infer_stream_error_code(exc: Exception) -> str:
    msg = str(exc or "").lower()
    if "state not initialized" in msg:
        return "STATE_NOT_INITIALIZED"
    if "novel not found" in msg:
        return "NOVEL_NOT_FOUND"
    if "empty plan" in msg:
        return "PLAN_EMPTY"
    if "init_state stream failed" in msg:
        return "INIT_STATE_EMPTY"
    if "disconnected" in msg:
        return "CLIENT_DISCONNECTED"
    if "event plan missing" in msg:
        return "EVENT_PLAN_MISSING"
    if "event binding required" in msg:
        return "EVENT_BINDING_REQUIRED"
    return f"STREAM_{exc.__class__.__name__.upper()}"


def require_existing_event_binding(req: RunModeRequest) -> str:
    event_id = str(req.existing_event_id or "").strip()
    if event_id.startswith("ev:timeline:"):
        return event_id
    raise ValueError("event binding required: choose an existing timeline event first")


def require_bound_timeline_event_exists(novel_id: str, event_id: str) -> str:
    st = load_state(novel_id)
    if not st:
        raise ValueError("novel not found")
    eid = str(event_id or "").strip()
    if not eid.startswith("ev:timeline:"):
        raise ValueError("event binding required: choose an existing timeline event first")
    for ev in st.world.timeline or []:
        if str(getattr(ev, "event_id", "") or "").strip() == eid:
            return eid
    raise ValueError("event binding required: choose an existing timeline event first (event_id not found in timeline)")


def require_event_plan_for_event(novel_id: str, event_id: str):
    rec = load_event_plan(novel_id, event_id)
    if not rec:
        raise ValueError("event plan missing for bound timeline event")
    return rec


def classify_event_plan_guard_error(exc: Exception) -> Tuple[str, str]:
    msg = str(exc or "").strip()
    low = msg.lower()
    if "event binding required" in low:
        return ("EVENT_BINDING_REQUIRED", "event binding required: choose an existing timeline event first")
    if "event plan missing" in low:
        return ("EVENT_PLAN_MISSING", "event plan missing for bound timeline event")
    if "novel not found" in low:
        return ("NOVEL_NOT_FOUND", "novel not found")
    return ("RUN_GUARD_FAILED", msg or "run guard failed")


def build_chapter_plan_from_event(
    *,
    chapter_index: int,
    req: RunModeRequest,
    inferred_time_slot: str | None,
    st: Any,
    event_plan_rec: Any,
    pov_ids: List[str],
) -> ChapterPlan:
    plan = event_plan_rec.plan
    time_slot = str(inferred_time_slot or plan.time_slot or st.continuity.time_slot or "未设置").strip()
    pov_id = pov_ids[0] if pov_ids else (st.continuity.pov_character_id or None)
    present_ids: List[str] = []
    if pov_id:
        present_ids.append(str(pov_id))
    present_ids.extend([str(x).strip() for x in (req.supporting_character_ids or []) if str(x).strip()])
    present_ids = [x for i, x in enumerate(present_ids) if x and x not in present_ids[:i]]
    who = [CharacterPresence(character_id=x) for x in present_ids]
    beat_rows: List[Beat] = []
    for i, item in enumerate((plan.progression or [])[:8], start=1):
        txt = str(item or "").strip()
        if not txt:
            continue
        beat_rows.append(Beat(beat_title=f"事件推进{i}", summary=txt, time_slot=time_slot))
    if not beat_rows:
        beat_rows.append(Beat(beat_title="事件推进", summary=str(plan.objective or "推进事件主线").strip(), time_slot=time_slot))
    next_state = st.model_copy(deep=True)
    next_state.continuity.time_slot = time_slot
    next_state.continuity.pov_character_id = pov_id
    next_state.continuity.who_is_present = who
    return ChapterPlan(
        chapter_index=int(chapter_index),
        time_slot=time_slot,
        pov_character_id=pov_id,
        who_is_present=who,
        beats=beat_rows,
        next_state=next_state,
    )


def unwrap_chapter_plan_payload(payload: Any) -> Dict[str, Any]:
    """
    兼容模型偶发返回包装层：
    - {"ChapterPlan": {...}}
    - {"result": {...}} / {"output": {...}}
    """
    if not isinstance(payload, dict):
        return {}
    if "ChapterPlan" in payload and isinstance(payload.get("ChapterPlan"), dict):
        return payload["ChapterPlan"]
    if "result" in payload and isinstance(payload.get("result"), dict):
        return payload["result"]
    if "output" in payload and isinstance(payload.get("output"), dict):
        return payload["output"]
    if len(payload) == 1:
        only = next(iter(payload.keys()))
        inner = payload.get(only)
        if isinstance(inner, dict) and str(only).strip().lower() in {"chapterplan", "result", "output"}:
            return inner
    return payload

