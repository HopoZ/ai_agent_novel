from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agents.persistence.event_plan_store import save_event_plan
from agents.persistence.storage import load_chapter, load_state, save_state
from agents.state.state_models import CharacterState, EventPlan, TimelineEvent
from webapp.backend.routes import novels
from webapp.backend.schemas import CreateNovelRequest, RunModeRequest


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


def _patch_agent_for_regression(monkeypatch):
    def fake_preview_input(**kwargs):
        state = load_state(kwargs["novel_id"])
        chapter_index = kwargs.get("chapter_index") or ((state.meta.current_chapter_index + 1) if state else 1)
        return {
            "novel_id": kwargs["novel_id"],
            "mode": kwargs["mode"],
            "chapter_index": int(chapter_index),
            "segments": {"user_task": kwargs.get("user_task", "")},
        }

    def fake_init_state_stream(*, novel_id: str, user_task: str, **_):
        state = load_state(novel_id)
        assert state is not None
        state.meta.initialized = True
        state.continuity.time_slot = "初始化阶段"
        state.characters = [
            CharacterState(
                character_id="hero",
                name="主角",
                description="回归测试角色",
                goals=["完成全链路"],
                known_facts=["系统处于测试模式"],
            )
        ]
        state.world.timeline = [
            TimelineEvent(
                event_id="ev:timeline:11111111111111111111111111111111",
                time_slot="第一幕",
                summary="故事启动",
            )
        ]
        save_state(novel_id, state)
        yield {"delta": f"[init]{user_task}"}
        yield {"done": True, "state": state.model_dump(mode="json"), "usage_metadata": {"total_tokens": 10}}

    def fake_plan_chapter_stream(
        *,
        novel_id: str,
        chapter_index: int,
        time_slot_override: Optional[str] = None,
        pov_character_ids_override: Optional[List[str]] = None,
        user_task: str,
        **_,
    ):
        state = load_state(novel_id)
        assert state is not None
        next_state = state.model_copy(deep=True)
        next_state.meta.initialized = True
        next_state.meta.current_chapter_index = int(chapter_index)
        next_state.continuity.time_slot = time_slot_override or f"章节{chapter_index}"
        if pov_character_ids_override:
            next_state.continuity.pov_character_id = pov_character_ids_override[0]
        else:
            next_state.continuity.pov_character_id = next_state.continuity.pov_character_id or "hero"
        plan = {
            "chapter_index": int(chapter_index),
            "time_slot": next_state.continuity.time_slot,
            "pov_character_id": next_state.continuity.pov_character_id,
            "who_is_present": [{"character_id": "hero", "role_in_scene": "执行者"}],
            "beats": [{"beat_title": "推进", "summary": user_task or "推进主线"}],
            "next_state": next_state.model_dump(mode="json"),
        }
        yield {"delta": f"[plan]{chapter_index}"}
        yield {"done": True, "plan": plan}

    def fake_write_chapter_text_stream(*, plan, write_mode: str = "generate", **_):
        chapter_index = int(getattr(plan, "chapter_index", 0) or 0)
        yield {"delta": f"第{chapter_index}章（{write_mode}）开场。"}
        yield {"delta": "情节推进并收束。", "usage_metadata": {"total_tokens": 20}}

    def fake_optimize_suggestions_stream(*_, **__):
        yield {"delta": "建议强化转折铺垫。", "usage_metadata": {"total_tokens": 8}}

    def fake_suggest_next_status(*, chapter_index: int, **_):
        return f"续写建议：推进到第{chapter_index + 1}章。"

    monkeypatch.setattr(novels.agent, "preview_input", fake_preview_input)
    monkeypatch.setattr(novels.agent, "init_state_stream", fake_init_state_stream)
    monkeypatch.setattr(novels.agent, "plan_chapter_stream", fake_plan_chapter_stream)
    monkeypatch.setattr(novels.agent, "write_chapter_text_stream", fake_write_chapter_text_stream)
    monkeypatch.setattr(novels.agent, "optimize_suggestions_stream", fake_optimize_suggestions_stream)
    monkeypatch.setattr(novels.agent, "suggest_next_status", fake_suggest_next_status)


def test_regression_matrix_three_novels(monkeypatch, tmp_path):
    monkeypatch.setenv("NOVEL_AGENT_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("NOVEL_AGENT_OUTPUTS_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("SKIP_FRONTEND_BUILD", "1")
    _patch_agent_for_regression(monkeypatch)

    novel_ids: List[str] = []
    event_id = "ev:timeline:11111111111111111111111111111111"

    for i in range(3):
        created = novels.create_novel(
            CreateNovelRequest(
                novel_title=f"回归样本{i + 1}",
                start_time_slot="第一幕",
                pov_character_id="hero",
                lore_tags=[],
            )
        )
        novel_id = str(created["novel_id"])
        novel_ids.append(novel_id)
        save_event_plan(
            novel_id,
            event_id,
            EventPlan(
                event_id=event_id,
                time_slot="第一幕",
                event_summary="故事启动",
                objective="推进主线",
                conflict="核心冲突",
                progression=["推进一", "推进二"],
                turning_points=["转折"],
                resolution_target="阶段收束",
                constraints=["不偏离设定"],
            ),
        )

        precheck_resp = novels.run_mode_stream(
            novel_id,
            RunModeRequest(mode="optimize_suggestions", user_task=f"样本{i + 1}预检错误码"),
            _FakeRequest(),
        )
        precheck_payloads = asyncio.run(_collect_stream_payloads(precheck_resp))
        err_frames = [p for p in precheck_payloads if p.get("event") == "error"]
        assert err_frames, "optimize without init should emit error"
        assert str(err_frames[-1].get("data", {}).get("error_code") or "").startswith("STATE_NOT_INITIALIZED")
        assert bool(str(err_frames[-1].get("data", {}).get("request_id") or "").strip())

        init_resp = novels.run_mode_stream(
            novel_id,
            RunModeRequest(mode="init_state", user_task=f"初始化样本{i + 1}"),
            _FakeRequest(),
        )
        init_payloads = asyncio.run(_collect_stream_payloads(init_resp))
        assert any(p.get("event") == "done" and p.get("data", {}).get("state_updated") for p in init_payloads)

        preview = novels.preview_mode_input(
            novel_id,
            RunModeRequest(mode="write_chapter", user_task=f"样本{i + 1}预览任务", existing_event_id=event_id),
        )
        assert preview["novel_id"] == novel_id

        write_resp = novels.run_mode_stream(
            novel_id,
            RunModeRequest(
                mode="write_chapter",
                user_task=f"样本{i + 1}第一章",
                existing_event_id=event_id,
                structure_risk_ack=True,
            ),
            _FakeRequest(),
        )
        write_payloads = asyncio.run(_collect_stream_payloads(write_resp))
        write_done = [p for p in write_payloads if p.get("event") == "done"]
        assert write_done, "write_chapter should emit done"
        assert bool(str(write_done[-1].get("data", {}).get("request_id") or "").strip())
        assert str(write_done[-1].get("data", {}).get("phase") or "") == "done"
        next_status = str(write_done[-1].get("data", {}).get("next_status") or "续写建议")

        continue_resp = novels.run_mode_stream(
            novel_id,
            RunModeRequest(
                mode="write_chapter",
                user_task=next_status,
                existing_event_id=event_id,
                structure_risk_ack=True,
            ),
            _FakeRequest(),
        )
        continue_payloads = asyncio.run(_collect_stream_payloads(continue_resp))
        assert any(p.get("event") == "done" for p in continue_payloads)

        expand_resp = novels.run_mode_stream(
            novel_id,
            RunModeRequest(
                mode="expand_chapter",
                user_task=f"样本{i + 1}扩写",
                existing_event_id=event_id,
                structure_risk_ack=True,
            ),
            _FakeRequest(),
        )
        expand_payloads = asyncio.run(_collect_stream_payloads(expand_resp))
        assert any(p.get("event") == "done" for p in expand_payloads)

        optimize_resp = novels.run_mode_stream(
            novel_id,
            RunModeRequest(mode="optimize_suggestions", user_task=f"样本{i + 1}优化"),
            _FakeRequest(),
        )
        optimize_payloads = asyncio.run(_collect_stream_payloads(optimize_resp))
        assert any(p.get("event") == "done" for p in optimize_payloads)

    # 流式中止与恢复：先中止一次，再恢复成功
    abort_novel = novel_ids[0]
    aborted_resp = novels.run_mode_stream(
        abort_novel,
        RunModeRequest(
            mode="write_chapter",
            user_task="中止测试",
            existing_event_id=event_id,
            structure_risk_ack=True,
        ),
        _FakeRequest(disconnect_after_calls=0),
    )
    aborted_payloads = asyncio.run(_collect_stream_payloads(aborted_resp))
    assert not any(p.get("event") == "done" for p in aborted_payloads)

    resumed_resp = novels.run_mode_stream(
        abort_novel,
        RunModeRequest(
            mode="write_chapter",
            user_task="恢复后继续",
            existing_event_id=event_id,
            structure_risk_ack=True,
        ),
        _FakeRequest(),
    )
    resumed_payloads = asyncio.run(_collect_stream_payloads(resumed_resp))
    assert any(p.get("event") == "done" for p in resumed_payloads)
    assert load_chapter(abort_novel, 1) is not None
