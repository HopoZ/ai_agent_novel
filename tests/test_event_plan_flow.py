from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agents.persistence.event_plan_store import save_event_plan
from agents.persistence.storage import load_chapter, load_state, save_state
from agents.state.state_models import CharacterState, EventPlan, TimelineEvent
from webapp.backend.routes import novels
from webapp.backend.schemas import CreateNovelRequest, EventPlanGenerateRequest, RunModeRequest


@dataclass
class _FakeRequest:
    disconnect_after_calls: Optional[int] = None
    calls: int = 0

    async def is_disconnected(self) -> bool:
        self.calls += 1
        if self.disconnect_after_calls is None:
            return False
        return self.calls > self.disconnect_after_calls


def _parse_sse_payloads(raw_text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for block in raw_text.split("\n\n"):
        if not block.strip():
            continue
        for line in block.splitlines():
            if not line.startswith("data: "):
                continue
            payload = json.loads(line[len("data: ") :].strip())
            if isinstance(payload, dict):
                out.append(payload)
    return out


async def _collect_stream_payloads(resp) -> List[Dict[str, Any]]:
    chunks: List[str] = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk.decode("utf-8"))
    return _parse_sse_payloads("".join(chunks))


def _seed_initialized_state_with_event(novel_id: str, event_id: str = "ev:timeline:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee") -> str:
    st = load_state(novel_id)
    assert st is not None
    st.meta.initialized = True
    st.continuity.pov_character_id = "hero"
    st.characters = [
        CharacterState(
            character_id="hero",
            name="主角",
            description="推进主线",
            goals=["完成任务"],
            known_facts=["与事件相关"],
        ),
        CharacterState(
            character_id="ally",
            name="配角",
            description="协助主角行动",
            goals=["辅助主角"],
            known_facts=["掌握线索"],
        ),
    ]
    st.world.timeline = [
        TimelineEvent(
            event_id=event_id,
            time_slot="第一幕",
            summary="事件一",
        )
    ]
    save_state(novel_id, st)
    return event_id


def test_event_plan_crud_and_write_guard(monkeypatch, tmp_path):
    monkeypatch.setenv("NOVEL_AGENT_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("NOVEL_AGENT_OUTPUTS_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("NOVEL_AGENT_LORES_DIR", str(tmp_path / "lores"))
    monkeypatch.setenv("SKIP_FRONTEND_BUILD", "1")

    created = novels.create_novel(
        CreateNovelRequest(
            novel_title="事件计划流",
            auto_generate_lore=False,
            lore_tags=["custom/base"],
        )
    )
    novel_id = str(created["novel_id"])
    event_id = _seed_initialized_state_with_event(novel_id)

    def _fake_plan_event(**kwargs):
        plan = EventPlan(
            event_id=event_id,
            time_slot="第一幕",
            event_summary="事件一",
            objective="推进主线",
            conflict="目标冲突",
            progression=["推进一", "推进二"],
            turning_points=["转折一"],
            resolution_target="阶段收束",
            constraints=["不偏离设定"],
        )
        return save_event_plan(novel_id, event_id, plan)

    monkeypatch.setattr(novels.agent, "plan_event", _fake_plan_event)
    rec = novels.generate_event_plan(
        novel_id,
        EventPlanGenerateRequest(event_id=event_id, user_task="生成事件计划"),
    )
    assert str(rec["event_id"]) == event_id

    listed = novels.get_event_plans(novel_id)
    assert int(listed["count"]) >= 1
    one = novels.get_event_plan(novel_id, event_id)
    assert str(one["event_id"]) == event_id

    novels.remove_event_plan(novel_id, event_id)
    listed_after = novels.get_event_plans(novel_id)
    assert not any(str(x.get("event_id") or "") == event_id for x in (listed_after.get("rows") or []))

    missing_resp = novels.run_mode_stream(
        novel_id,
        RunModeRequest(
            mode="write_chapter",
            user_task="缺失计划拦截",
            existing_event_id=event_id,
            structure_risk_ack=True,
        ),
        _FakeRequest(),
    )
    missing_payloads = asyncio.run(_collect_stream_payloads(missing_resp))
    missing_errors = [p for p in missing_payloads if p.get("event") == "error"]
    assert missing_errors
    assert str(missing_errors[-1].get("data", {}).get("error_code") or "") == "EVENT_PLAN_MISSING"

    save_event_plan(
        novel_id,
        event_id,
        EventPlan(
            event_id=event_id,
            time_slot="第一幕",
            event_summary="事件一",
            objective="推进主线",
            conflict="目标冲突",
            progression=["推进一", "推进二"],
            turning_points=["转折一"],
            resolution_target="阶段收束",
            constraints=["不偏离设定"],
        ),
    )

    def _fake_write_chapter_text_stream(*, plan, **_):
        chapter_index = int(getattr(plan, "chapter_index", 1))
        yield {"delta": f"第{chapter_index}章正文。", "usage_metadata": {"total_tokens": 5}}

    monkeypatch.setattr(novels.agent, "write_chapter_text_stream", _fake_write_chapter_text_stream)
    monkeypatch.setattr(novels.agent, "suggest_next_status", lambda **_: "下章建议")

    ok_resp = novels.run_mode_stream(
        novel_id,
        RunModeRequest(
            mode="write_chapter",
            user_task="有计划可写",
            existing_event_id=event_id,
            structure_risk_ack=True,
        ),
        _FakeRequest(),
    )
    ok_payloads = asyncio.run(_collect_stream_payloads(ok_resp))
    done_rows = [p for p in ok_payloads if p.get("event") == "done"]
    assert done_rows
    done_data = done_rows[-1].get("data", {}) or {}
    auto = done_data.get("auto_rejudge", {}) or {}
    assert isinstance(auto, dict)
    assert bool((auto.get("effective_pov_ids") or []))
    assert not bool(auto.get("manual_pov"))
    chapter_idx = int(done_rows[-1].get("data", {}).get("chapter_index") or 0)
    assert chapter_idx >= 1
    chapter = load_chapter(novel_id, chapter_idx)
    assert chapter is not None
    assert bool(str(chapter.source_event_plan_id or "").strip())

    manual_resp = novels.run_mode_stream(
        novel_id,
        RunModeRequest(
            mode="write_chapter",
            user_task="手动指定优先",
            existing_event_id=event_id,
            pov_character_ids_override=["hero"],
            supporting_character_ids=["ally"],
            structure_risk_ack=True,
        ),
        _FakeRequest(),
    )
    manual_payloads = asyncio.run(_collect_stream_payloads(manual_resp))
    manual_done = [p for p in manual_payloads if p.get("event") == "done"]
    assert manual_done
    manual_auto = (manual_done[-1].get("data", {}) or {}).get("auto_rejudge", {}) or {}
    assert bool(manual_auto.get("manual_pov"))
    assert bool(manual_auto.get("manual_supporting"))
    assert "hero" in [str(x) for x in (manual_auto.get("effective_pov_ids") or [])]
