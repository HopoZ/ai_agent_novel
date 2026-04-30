from __future__ import annotations

import multiprocessing as mp
from queue import Empty
from typing import Any, Dict, Iterator, Optional

from agents.novel import NovelAgent
from agents.state.state_models import ChapterPlan, EventPlan


def _writer_process_main(payload: Dict[str, Any], out_q: mp.Queue) -> None:
    try:
        agent = NovelAgent()
        plan = ChapterPlan.model_validate(payload["plan"])
        event_plan_payload = payload.get("event_plan")
        event_plan = EventPlan.model_validate(event_plan_payload) if isinstance(event_plan_payload, dict) else None

        for item in agent.write_chapter_text_stream(
            novel_id=str(payload["novel_id"]),
            plan=plan,
            user_task=str(payload["user_task"]),
            minimal_state_for_prompt=bool(payload.get("minimal_state_for_prompt", False)),
            lore_tags=(list(payload.get("lore_tags") or []) or None),
            time_slot_hint=(str(payload.get("time_slot_hint") or "").strip() or None),
            pov_character_ids_override=(list(payload.get("pov_character_ids_override") or []) or None),
            supporting_character_ids=(list(payload.get("supporting_character_ids") or []) or None),
            llm_options=(dict(payload.get("llm_options") or {}) or None),
            timeline_event_focus_id=(str(payload.get("timeline_event_focus_id") or "").strip() or None),
            write_mode=str(payload.get("write_mode") or "generate"),
            event_plan=event_plan,
            omit_world_timeline=bool(payload.get("omit_world_timeline", False)),
        ):
            out_q.put(
                {
                    "type": "chunk",
                    "delta": str(item.get("delta", "") or ""),
                    "usage_metadata": (item.get("usage_metadata") if isinstance(item.get("usage_metadata"), dict) else {}),
                }
            )
        out_q.put({"type": "done"})
    except Exception as exc:
        out_q.put({"type": "error", "message": str(exc)})


def stream_write_chapter_text_ipc(
    *,
    novel_id: str,
    plan: ChapterPlan,
    user_task: str,
    minimal_state_for_prompt: bool = False,
    lore_tags: Optional[list[str]] = None,
    time_slot_hint: Optional[str] = None,
    pov_character_ids_override: Optional[list[str]] = None,
    supporting_character_ids: Optional[list[str]] = None,
    llm_options: Optional[Dict[str, Any]] = None,
    timeline_event_focus_id: Optional[str] = None,
    write_mode: str = "generate",
    event_plan: Optional[EventPlan] = None,
    omit_world_timeline: bool = False,
) -> Iterator[Dict[str, Any]]:
    ctx = mp.get_context("spawn")
    out_q: mp.Queue = ctx.Queue()
    payload: Dict[str, Any] = {
        "novel_id": novel_id,
        "plan": plan.model_dump(mode="json"),
        "user_task": user_task,
        "minimal_state_for_prompt": minimal_state_for_prompt,
        "lore_tags": list(lore_tags or []),
        "time_slot_hint": time_slot_hint,
        "pov_character_ids_override": list(pov_character_ids_override or []),
        "supporting_character_ids": list(supporting_character_ids or []),
        "llm_options": dict(llm_options or {}),
        "timeline_event_focus_id": timeline_event_focus_id,
        "write_mode": write_mode,
        "event_plan": (event_plan.model_dump(mode="json") if event_plan else None),
        "omit_world_timeline": omit_world_timeline,
    }
    proc = ctx.Process(target=_writer_process_main, args=(payload, out_q), daemon=True)
    proc.start()

    try:
        while True:
            try:
                msg = out_q.get(timeout=0.2)
            except Empty:
                if not proc.is_alive():
                    break
                continue
            mtype = str(msg.get("type") or "")
            if mtype == "chunk":
                yield {
                    "delta": str(msg.get("delta", "") or ""),
                    "usage_metadata": (msg.get("usage_metadata") if isinstance(msg.get("usage_metadata"), dict) else {}),
                }
            elif mtype == "done":
                break
            elif mtype == "error":
                raise RuntimeError(str(msg.get("message") or "ipc writer failed"))
    finally:
        proc.join(timeout=0.5)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=1.0)
