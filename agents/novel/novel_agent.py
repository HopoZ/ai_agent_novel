from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional, Set, Tuple

from langchain.messages import HumanMessage, SystemMessage

from agents._internal_marks import z7_module_mark
from agents.persistence.graph_tables import (
    hydrate_state_character_relationships,
    persist_chapter_artifacts,
    validate_timeline_event_id,
)
from agents.lore.loader import LoreLoader
from agents.lore.lore_runtime import build_lore_summary_llm as build_lore_summary_llm_runtime
from agents.lore.lore_runtime import build_lorebook
from agents.prompt.prompt_builders import (
    build_init_state_prompt,
    build_next_status_prompt,
    build_optimize_suggestions_prompt,
    build_plan_chapter_prompt,
    build_write_chapter_prompt,
)
from agents.state.state_compactor import (
    compact_state_for_prompt as compact_state_for_prompt_runtime,
    format_state_for_prompt as format_state_for_prompt_runtime,
    select_related_character_ids as select_related_character_ids_runtime,
)
from agents.state.state_merge import merge_state as merge_state_runtime
from agents.state.state_models import ChapterPlan, ChapterRecord, ContinuityState, NovelMeta, NovelState
from agents.persistence.storage import (
    ensure_novel_dirs,
    load_state,
    save_state,
)
from agents.text_utils import parse_ai_chunk_text, parse_ai_text, write_outputs_txt

from .llm_client import bind_llm_options, init_deepseek_chat
from .llm_json import extract_json_object, json_load_with_retry
from .structured_invoke import invoke_pydantic_json
from .timeline_focus import resolve_timeline_focus_event_id


logger = logging.getLogger("novel_agent")
_MODULE_REV = z7_module_mark("na")


@dataclass
class RunResult:
    novel_id: str
    mode: str
    chapter_index: Optional[int]
    state_updated: bool
    content: Optional[str] = None
    plan: Optional[ChapterPlan] = None
    usage_metadata: Optional[Dict[str, Any]] = None
    next_status: Optional[str] = None


class NovelAgent:
    """
    一个“稳定写小说”的 agent 引擎：
    - 先规划 beats + 生成 next_state（严格 JSON）
    - 再写正文（纯文本）
    - 保存完整 world_state / 人物状态 / 时间段 / 出场角色
    """

    def __init__(self, lore_loader: Optional[LoreLoader] = None):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        # 设定目录只在 LoreLoader 默认；测试可注入自定义 loader
        self.lore_loader = lore_loader or LoreLoader()
        self.model = None  # 懒加载：避免未配置 key 时无法启动 Web

    def _get_model(self):
        if self.model is None:
            self.model = init_deepseek_chat()
        return self.model

    def _model_for_call(self, llm_options: Optional[Dict[str, Any]] = None):
        return bind_llm_options(self._get_model(), llm_options)

    def _load_state_hydrated(self, novel_id: str) -> Optional[NovelState]:
        state = load_state(novel_id)
        if not state:
            return None
        return hydrate_state_character_relationships(novel_id, state)

    def _lorebook(self, lore_tags: Optional[list[str]] = None, lore_summary_id: Optional[str] = None) -> str:
        # lore_summary_id 已废弃；按 tags + 单 tag 缓存读取 lorebook
        return build_lorebook(self.lore_loader, lore_tags=lore_tags)

    def build_lore_summary_llm(self, tags: list[str], force: bool = False) -> Dict[str, Any]:
        return build_lore_summary_llm_runtime(
            model=self._get_model(),
            lore_loader=self.lore_loader,
            tags=tags,
            force=force,
        )

    def _select_related_character_ids(
        self,
        state: NovelState,
        user_task: str,
        pov_character_ids_override: Optional[list[str]] = None,
        supporting_character_ids: Optional[list[str]] = None,
    ) -> Set[str]:
        return select_related_character_ids_runtime(
            state=state,
            user_task=user_task,
            pov_character_ids_override=pov_character_ids_override,
            supporting_character_ids=supporting_character_ids,
        )

    def _compact_state_for_prompt(
        self,
        state: NovelState,
        user_task: str,
        time_slot_hint: Optional[str] = None,
        pov_character_ids_override: Optional[list[str]] = None,
        supporting_character_ids: Optional[list[str]] = None,
        minimal_context: bool = False,
        strict_no_supporting: bool = False,
        timeline_n: int = 6,
        max_chars: int = 9000,
        novel_id: Optional[str] = None,
        focus_timeline_event_id: Optional[str] = None,
    ) -> str:
        return compact_state_for_prompt_runtime(
            state=state,
            user_task=user_task,
            time_slot_hint=time_slot_hint,
            pov_character_ids_override=pov_character_ids_override,
            supporting_character_ids=supporting_character_ids,
            minimal_context=minimal_context,
            strict_no_supporting=strict_no_supporting,
            timeline_n=timeline_n,
            max_chars=max_chars,
            novel_id=novel_id,
            focus_timeline_event_id=focus_timeline_event_id,
        )

    def _format_state_for_prompt(self, state: NovelState, max_chars: int = 12000) -> str:
        return format_state_for_prompt_runtime(state=state, max_chars=max_chars)

    def create_novel_stub(
        self,
        novel_id: str,
        novel_title: Optional[str] = None,
        start_time_slot: Optional[str] = None,
        pov_character_id: Optional[str] = None,
        lore_tags: Optional[list[str]] = None,
    ) -> NovelState:
        ensure_novel_dirs(novel_id)

        state = NovelState(
            meta=NovelMeta(
                novel_id=novel_id,
                initialized=False,
                current_chapter_index=0,
                lore_tags=lore_tags or [],
                novel_title=novel_title,
            ),
            continuity=ContinuityState(
                time_slot=start_time_slot or "未指定（由模型选择）",
                pov_character_id=pov_character_id,
                who_is_present=[],
            ),
            characters=[],
            world={},
            recent_summaries=[],
        )
        save_state(novel_id, state)
        return state

    def _init_state_impl(
        self,
        novel_id: str,
        user_task: str,
        lore_tags: Optional[list[str]] = None,
        lore_summary_id: Optional[str] = None,
        llm_options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[NovelState, Dict[str, Any]]:
        state = self._load_state_hydrated(novel_id)
        if not state:
            raise ValueError(f"novel_id not found: {novel_id}")

        lorebook = self._lorebook(lore_tags, lore_summary_id=lore_summary_id)
        state_context = self._compact_state_for_prompt(state, user_task=user_task)

        system, human = build_init_state_prompt(
            user_task=user_task,
            state_context=state_context,
            lorebook=lorebook,
        )

        plan_json, usage = self._invoke_json(
            system,
            human,
            root_model=NovelState,
            return_usage=True,
            llm_options=llm_options,
        )
        plan_json.meta.initialized = True
        # 防止“补初始化”场景把已有章节进度回退到 0
        plan_json.meta.current_chapter_index = max(
            state.meta.current_chapter_index,
            plan_json.meta.current_chapter_index,
        )
        # 记录本小说使用的 lore_tags，后续各模式可沿用
        plan_json.meta.lore_tags = lore_tags or state.meta.lore_tags
        save_state(novel_id, plan_json)
        return plan_json, usage

    def init_state(
        self,
        novel_id: str,
        user_task: str,
        lore_tags: Optional[list[str]] = None,
        lore_summary_id: Optional[str] = None,
        llm_options: Optional[Dict[str, Any]] = None,
    ) -> NovelState:
        state, _ = self._init_state_impl(
            novel_id=novel_id,
            user_task=user_task,
            lore_tags=lore_tags,
            lore_summary_id=lore_summary_id,
            llm_options=llm_options,
        )
        return state

    def init_state_with_usage(
        self,
        novel_id: str,
        user_task: str,
        lore_tags: Optional[list[str]] = None,
        lore_summary_id: Optional[str] = None,
        llm_options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[NovelState, Dict[str, Any]]:
        return self._init_state_impl(
            novel_id=novel_id,
            user_task=user_task,
            lore_tags=lore_tags,
            lore_summary_id=lore_summary_id,
            llm_options=llm_options,
        )

    def init_state_stream(
        self,
        novel_id: str,
        user_task: str,
        lore_tags: Optional[list[str]] = None,
        lore_summary_id: Optional[str] = None,
        llm_options: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        流式生成 init_state。
        - 每个 chunk：{"delta": str, "usage_metadata": {...}}
        - 结束时：{"done": True, "state": {...}, "usage_metadata": {...}}
        """
        state = self._load_state_hydrated(novel_id)
        if not state:
            raise ValueError(f"novel_id not found: {novel_id}")

        lorebook = self._lorebook(lore_tags, lore_summary_id=lore_summary_id)
        state_context = self._compact_state_for_prompt(state=state, user_task=user_task)
        system, human = build_init_state_prompt(
            user_task=user_task,
            state_context=state_context,
            lorebook=lorebook,
        )

        messages = [SystemMessage(system), HumanMessage(human)]
        chunks: list[str] = []
        final_usage: Dict[str, Any] = {}
        model = self._model_for_call(llm_options)
        for chunk in model.stream(messages):
            text = parse_ai_chunk_text(chunk)
            usage = getattr(chunk, "usage_metadata", None) or {}
            if text:
                chunks.append(text)
            if isinstance(usage, dict) and usage:
                final_usage = usage
            if text or usage:
                yield {"delta": text, "usage_metadata": usage}

        raw_text = "".join(chunks)
        data = json.loads(extract_json_object(raw_text))
        plan_json = NovelState.model_validate(data)
        plan_json.meta.initialized = True
        plan_json.meta.current_chapter_index = max(
            state.meta.current_chapter_index,
            plan_json.meta.current_chapter_index,
        )
        plan_json.meta.lore_tags = lore_tags or state.meta.lore_tags
        save_state(novel_id, plan_json)
        yield {"done": True, "state": plan_json.model_dump(mode="json"), "usage_metadata": final_usage}

    def plan_chapter(
        self,
        novel_id: str,
        user_task: str,
        chapter_index: int,
        time_slot_override: Optional[str] = None,
        pov_character_ids_override: Optional[list[str]] = None,
        supporting_character_ids: Optional[list[str]] = None,
        minimal_state_for_prompt: bool = False,
        lore_tags: Optional[list[str]] = None,
        lore_summary_id: Optional[str] = None,
        llm_options: Optional[Dict[str, Any]] = None,
        timeline_event_focus_id: Optional[str] = None,
    ) -> ChapterPlan:
        state = self._load_state_hydrated(novel_id)
        if not state:
            raise ValueError(f"novel_id not found: {novel_id}")
        if not state.meta.initialized:
            raise ValueError("state 尚未初始化。请先用 mode=`init_state` 初始化。")

        strict_no_supporting = bool(pov_character_ids_override) and not bool(supporting_character_ids)
        lorebook = self._lorebook(lore_tags or state.meta.lore_tags, lore_summary_id=lore_summary_id)
        focus_eid = resolve_timeline_focus_event_id(
            novel_id,
            state,
            chapter_index,
            time_slot_override,
            timeline_event_focus_id,
        )
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            time_slot_hint=time_slot_override,
            pov_character_ids_override=pov_character_ids_override,
            supporting_character_ids=supporting_character_ids,
            minimal_context=minimal_state_for_prompt,
            strict_no_supporting=strict_no_supporting,
            novel_id=novel_id,
            focus_timeline_event_id=focus_eid,
        )
        continuity_hint = {
            "time_slot_override": time_slot_override,
            "pov_character_ids_override": pov_character_ids_override or [],
            "supporting_character_ids": supporting_character_ids or [],
        }

        system, human = build_plan_chapter_prompt(
            user_task=user_task,
            chapter_index=chapter_index,
            continuity_hint=continuity_hint,
            state_context=state_context,
            lorebook=lorebook,
            strict_no_supporting=strict_no_supporting,
        )

        return self._invoke_json(system, human, root_model=ChapterPlan, llm_options=llm_options)

    def plan_chapter_stream(
        self,
        novel_id: str,
        user_task: str,
        chapter_index: int,
        time_slot_override: Optional[str] = None,
        pov_character_ids_override: Optional[list[str]] = None,
        supporting_character_ids: Optional[list[str]] = None,
        minimal_state_for_prompt: bool = False,
        lore_tags: Optional[list[str]] = None,
        lore_summary_id: Optional[str] = None,
        llm_options: Optional[Dict[str, Any]] = None,
        timeline_event_focus_id: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        流式生成章节规划（原始 JSON 文本）。
        - chunk: {"delta": str, "usage_metadata": {...}}
        - done: {"done": True, "plan": {...}, "usage_metadata": {...}}
        """
        state = self._load_state_hydrated(novel_id)
        if not state:
            raise ValueError(f"novel_id not found: {novel_id}")
        if not state.meta.initialized:
            raise ValueError("state 尚未初始化。请先用 mode=`init_state` 初始化。")

        strict_no_supporting = bool(pov_character_ids_override) and not bool(supporting_character_ids)
        lorebook = self._lorebook(lore_tags or state.meta.lore_tags, lore_summary_id=lore_summary_id)
        focus_eid = resolve_timeline_focus_event_id(
            novel_id,
            state,
            chapter_index,
            time_slot_override,
            timeline_event_focus_id,
        )
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            time_slot_hint=time_slot_override,
            pov_character_ids_override=pov_character_ids_override,
            supporting_character_ids=supporting_character_ids,
            minimal_context=minimal_state_for_prompt,
            strict_no_supporting=strict_no_supporting,
            novel_id=novel_id,
            focus_timeline_event_id=focus_eid,
        )
        continuity_hint = {
            "time_slot_override": time_slot_override,
            "pov_character_ids_override": pov_character_ids_override or [],
            "supporting_character_ids": supporting_character_ids or [],
        }
        system, human = build_plan_chapter_prompt(
            user_task=user_task,
            chapter_index=chapter_index,
            continuity_hint=continuity_hint,
            state_context=state_context,
            lorebook=lorebook,
            strict_no_supporting=strict_no_supporting,
        )

        messages = [SystemMessage(system), HumanMessage(human)]
        chunks: list[str] = []
        final_usage: Dict[str, Any] = {}
        model = self._model_for_call(llm_options)
        for chunk in model.stream(messages):
            text = parse_ai_chunk_text(chunk)
            usage = getattr(chunk, "usage_metadata", None) or {}
            if text:
                chunks.append(text)
            if isinstance(usage, dict) and usage:
                final_usage = usage
            if text or usage:
                yield {"delta": text, "usage_metadata": usage}

        raw_text = "".join(chunks)

        def llm_fix_invoke(fix_prompt: str) -> str:
            fix_messages = [SystemMessage(system), HumanMessage(fix_prompt)]
            resp = model.invoke(fix_messages)
            return parse_ai_text(resp)

        data = json_load_with_retry(
            raw_text=raw_text,
            fix_prompt=(
                "你输出的不是合法 JSON。请仅输出一个合法 JSON 对象，内容与原意一致，"
                "并确保结构符合 ChapterPlan（不要输出任何额外文本）。\n\n"
                "原始输出：\n"
                f"{raw_text}\n"
            ),
            llm_invoke_fn=llm_fix_invoke,
            logger=logger,
        )
        plan = ChapterPlan.model_validate(data)
        yield {"done": True, "plan": plan.model_dump(mode="json"), "usage_metadata": final_usage}

    @staticmethod
    def merge_state(base: NovelState, patch: NovelState) -> NovelState:
        return merge_state_runtime(base=base, patch=patch)

    def write_chapter_text(
        self,
        novel_id: str,
        plan: ChapterPlan,
        user_task: str,
        minimal_state_for_prompt: bool = False,
        lore_tags: Optional[list[str]] = None,
        lore_summary_id: Optional[str] = None,
        time_slot_hint: Optional[str] = None,
        pov_character_ids_override: Optional[list[str]] = None,
        supporting_character_ids: Optional[list[str]] = None,
        llm_options: Optional[Dict[str, Any]] = None,
        timeline_event_focus_id: Optional[str] = None,
        write_mode: str = "generate",
    ) -> Tuple[str, Dict[str, Any]]:
        state = self._load_state_hydrated(novel_id)
        if not state:
            raise ValueError(f"novel_id not found: {novel_id}")

        strict_no_supporting = bool(pov_character_ids_override) and not bool(supporting_character_ids)
        lorebook = self._lorebook(lore_tags or state.meta.lore_tags, lore_summary_id=lore_summary_id)
        focus_eid = resolve_timeline_focus_event_id(
            novel_id,
            state,
            plan.chapter_index,
            time_slot_hint or plan.time_slot,
            timeline_event_focus_id,
        )
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            time_slot_hint=time_slot_hint,
            pov_character_ids_override=pov_character_ids_override,
            supporting_character_ids=supporting_character_ids,
            minimal_context=minimal_state_for_prompt,
            strict_no_supporting=strict_no_supporting,
            novel_id=novel_id,
            focus_timeline_event_id=focus_eid,
        )
        system, human = build_write_chapter_prompt(
            user_task=user_task,
            state_context=state_context,
            lorebook=lorebook,
            plan=plan,
            strict_no_supporting=strict_no_supporting,
            write_mode=write_mode,
        )

        messages = [SystemMessage(system), HumanMessage(human)]
        logger.info("Writing chapter %s ...", plan.chapter_index)
        model = self._model_for_call(llm_options)
        resp = model.invoke(messages)
        text = parse_ai_text(resp)
        usage = getattr(resp, "usage_metadata", None) or {}
        return text.strip(), usage

    def write_chapter_text_stream(
        self,
        novel_id: str,
        plan: ChapterPlan,
        user_task: str,
        minimal_state_for_prompt: bool = False,
        lore_tags: Optional[list[str]] = None,
        lore_summary_id: Optional[str] = None,
        time_slot_hint: Optional[str] = None,
        pov_character_ids_override: Optional[list[str]] = None,
        supporting_character_ids: Optional[list[str]] = None,
        llm_options: Optional[Dict[str, Any]] = None,
        timeline_event_focus_id: Optional[str] = None,
        write_mode: str = "generate",
    ) -> Iterator[Dict[str, Any]]:
        """
        流式生成章节正文。
        每个 chunk 返回:
        - delta: 文本增量
        - usage_metadata: 可能存在的 token 统计（不同 provider 可能只在末 chunk 提供）
        """
        state = self._load_state_hydrated(novel_id)
        if not state:
            raise ValueError(f"novel_id not found: {novel_id}")

        strict_no_supporting = bool(pov_character_ids_override) and not bool(supporting_character_ids)
        lorebook = self._lorebook(lore_tags or state.meta.lore_tags, lore_summary_id=lore_summary_id)
        focus_eid = resolve_timeline_focus_event_id(
            novel_id,
            state,
            plan.chapter_index,
            time_slot_hint or plan.time_slot,
            timeline_event_focus_id,
        )
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            time_slot_hint=time_slot_hint,
            pov_character_ids_override=pov_character_ids_override,
            supporting_character_ids=supporting_character_ids,
            minimal_context=minimal_state_for_prompt,
            strict_no_supporting=strict_no_supporting,
            novel_id=novel_id,
            focus_timeline_event_id=focus_eid,
        )
        system, human = build_write_chapter_prompt(
            user_task=user_task,
            state_context=state_context,
            lorebook=lorebook,
            plan=plan,
            strict_no_supporting=strict_no_supporting,
            write_mode=write_mode,
        )

        messages = [SystemMessage(system), HumanMessage(human)]
        logger.info("Streaming write chapter %s ...", plan.chapter_index)
        model = self._model_for_call(llm_options)
        for chunk in model.stream(messages):
            text = parse_ai_chunk_text(chunk)
            usage = getattr(chunk, "usage_metadata", None) or {}
            if text or usage:
                yield {"delta": text, "usage_metadata": usage}

    def optimize_suggestions_invoke(
        self,
        novel_id: str,
        user_task: str,
        lore_tags: Optional[list[str]] = None,
        lore_summary_id: Optional[str] = None,
        llm_options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        state = self._load_state_hydrated(novel_id)
        if not state:
            raise ValueError(f"novel_id not found: {novel_id}")
        if not state.meta.initialized:
            raise ValueError("state not initialized. please run init_state first")
        lorebook = self._lorebook(lore_tags or state.meta.lore_tags, lore_summary_id=lore_summary_id)
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            novel_id=novel_id,
            timeline_n=4,
            max_chars=10000,
        )
        system, human = build_optimize_suggestions_prompt(
            user_task=user_task,
            state_context=state_context,
            lorebook=lorebook,
        )
        model = self._model_for_call(llm_options)
        resp = model.invoke([SystemMessage(system), HumanMessage(human)])
        text = parse_ai_text(resp).strip()
        usage = getattr(resp, "usage_metadata", None) or {}
        return text, usage

    def optimize_suggestions_stream(
        self,
        novel_id: str,
        user_task: str,
        lore_tags: Optional[list[str]] = None,
        lore_summary_id: Optional[str] = None,
        llm_options: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Dict[str, Any]]:
        state = self._load_state_hydrated(novel_id)
        if not state:
            raise ValueError(f"novel_id not found: {novel_id}")
        if not state.meta.initialized:
            raise ValueError("state not initialized. please run init_state first")
        lorebook = self._lorebook(lore_tags or state.meta.lore_tags, lore_summary_id=lore_summary_id)
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            novel_id=novel_id,
            timeline_n=4,
            max_chars=10000,
        )
        system, human = build_optimize_suggestions_prompt(
            user_task=user_task,
            state_context=state_context,
            lorebook=lorebook,
        )
        model = self._model_for_call(llm_options)
        for chunk in model.stream([SystemMessage(system), HumanMessage(human)]):
            text = parse_ai_chunk_text(chunk)
            usage = getattr(chunk, "usage_metadata", None) or {}
            if text or usage:
                yield {"delta": text, "usage_metadata": usage}

    def suggest_next_status(
        self,
        novel_id: str,
        user_task: str,
        chapter_index: int,
        latest_content: str,
        llm_options: Optional[Dict[str, Any]] = None,
        timeline_event_focus_id: Optional[str] = None,
    ) -> str:
        """
        独立生成“下章建议”，不参与当前章节 plan/write。
        """
        state = self._load_state_hydrated(novel_id)
        if not state:
            return ""
        focus_eid = resolve_timeline_focus_event_id(
            novel_id,
            state,
            chapter_index,
            state.continuity.time_slot,
            timeline_event_focus_id,
        )
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            time_slot_hint=state.continuity.time_slot,
            timeline_n=4,
            max_chars=7000,
            novel_id=novel_id,
            focus_timeline_event_id=focus_eid,
        )
        content = (latest_content or "").strip()
        if len(content) > 2500:
            content = content[-2500:]
        system, human = build_next_status_prompt(
            user_task=user_task,
            chapter_index=chapter_index,
            state_context=state_context,
            latest_content=content,
        )
        model = self._model_for_call(llm_options)
        resp = model.invoke([SystemMessage(system), HumanMessage(human)])
        return parse_ai_text(resp).strip()

    def run(
        self,
        novel_id: str,
        mode: str,
        user_task: str,
        chapter_index: Optional[int] = None,
        chapter_preset_name: Optional[str] = None,
        time_slot_override: Optional[str] = None,
        manual_time_slot: bool = False,
        pov_character_ids_override: Optional[list[str]] = None,
        supporting_character_ids: Optional[list[str]] = None,
        lore_tags: Optional[list[str]] = None,
        lore_summary_id: Optional[str] = None,
        llm_options: Optional[Dict[str, Any]] = None,
        timeline_event_focus_id: Optional[str] = None,
    ) -> RunResult:
        state = self._load_state_hydrated(novel_id)
        if not state:
            raise ValueError(f"novel_id not found: {novel_id}")

        if mode == "init_state":
            self.init_state(
                novel_id,
                user_task=user_task,
                lore_tags=lore_tags,
                lore_summary_id=lore_summary_id,
                llm_options=llm_options,
            )
            return RunResult(novel_id=novel_id, mode=mode, chapter_index=None, state_updated=True, content=None)

        if mode == "optimize_suggestions":
            if not state.meta.initialized:
                raise ValueError("state not initialized. please run init_state first")
            text, usage = self.optimize_suggestions_invoke(
                novel_id=novel_id,
                user_task=user_task,
                lore_tags=lore_tags,
                lore_summary_id=lore_summary_id,
                llm_options=llm_options,
            )
            return RunResult(
                novel_id=novel_id,
                mode=mode,
                chapter_index=None,
                state_updated=False,
                content=text,
                usage_metadata=usage,
            )

        if mode in {"plan_only", "write_chapter", "revise_chapter", "expand_chapter"}:
            if not state.meta.initialized:
                raise ValueError("state not initialized. please run init_state first")

            if chapter_index is None:
                chapter_index = state.meta.current_chapter_index + 1

            plan = self.plan_chapter(
                novel_id=novel_id,
                user_task=user_task,
                chapter_index=chapter_index,
                time_slot_override=time_slot_override,
                pov_character_ids_override=pov_character_ids_override,
                supporting_character_ids=supporting_character_ids,
                minimal_state_for_prompt=manual_time_slot,
                lore_tags=lore_tags,
                lore_summary_id=lore_summary_id,
                llm_options=llm_options,
                timeline_event_focus_id=timeline_event_focus_id,
            )
            # 允许 plan.next_state 是“补丁”，这里合并成完整状态再落盘
            try:
                plan.next_state = self.merge_state(state, plan.next_state)
            except Exception as e:
                logger.warning("merge_state failed, fallback to plan.next_state. err=%s", e)

            if mode == "plan_only":
                # 不落正文，但保存 plan 与 next_state（更新状态）
                record = ChapterRecord(
                    chapter_index=chapter_index,
                    chapter_preset_name=chapter_preset_name,
                    timeline_event_id=validate_timeline_event_id(plan.next_state, timeline_event_focus_id),
                    time_slot=plan.time_slot,
                    pov_character_id=plan.pov_character_id,
                    who_is_present=plan.who_is_present,
                    beats=plan.beats,
                    content="",
                    usage_metadata={},
                )
                persist_chapter_artifacts(
                    novel_id=novel_id,
                    chapter=record,
                    next_state=plan.next_state,
                    chapter_preset_name=chapter_preset_name,
                )
                return RunResult(
                    novel_id=novel_id,
                    mode=mode,
                    chapter_index=chapter_index,
                    state_updated=True,
                    content=None,
                    plan=plan,
                )

            # write_chapter / revise_chapter / expand_chapter：先写正文，再落盘章节
            write_mode = "expand" if mode == "expand_chapter" else "generate"
            content_text, usage = self.write_chapter_text(
                novel_id=novel_id,
                plan=plan,
                user_task=user_task,
                minimal_state_for_prompt=manual_time_slot,
                lore_tags=lore_tags,
                lore_summary_id=lore_summary_id,
                time_slot_hint=time_slot_override,
                pov_character_ids_override=pov_character_ids_override,
                supporting_character_ids=supporting_character_ids,
                llm_options=llm_options,
                timeline_event_focus_id=timeline_event_focus_id,
                write_mode=write_mode,
            )

            if mode == "revise_chapter":
                # revise 仍以 plan 的 next_state 为准
                pass

            record = ChapterRecord(
                chapter_index=chapter_index,
                chapter_preset_name=chapter_preset_name,
                timeline_event_id=validate_timeline_event_id(plan.next_state, timeline_event_focus_id),
                time_slot=plan.time_slot,
                pov_character_id=plan.pov_character_id,
                who_is_present=plan.who_is_present,
                beats=plan.beats,
                content=content_text,
                usage_metadata=usage,
            )
            next_state = plan.next_state
            persist_chapter_artifacts(
                novel_id=novel_id,
                chapter=record,
                next_state=next_state,
                chapter_preset_name=chapter_preset_name,
            )

            # 同步写出纯文本到 outputs/（保持脚本版的落盘习惯）
            try:
                title = state.meta.novel_title or "未命名小说"
                out_path = write_outputs_txt(title, chapter_index, content_text)
                logger.info("Wrote outputs txt: %s", out_path)
            except Exception as e:
                logger.warning("Failed to write outputs txt: %s", e)

            # 独立生成“下章建议”，不回流参与本章写作
            next_status = ""
            try:
                next_status = self.suggest_next_status(
                    novel_id=novel_id,
                    user_task=user_task,
                    chapter_index=chapter_index,
                    latest_content=content_text,
                    llm_options=llm_options,
                    timeline_event_focus_id=timeline_event_focus_id,
                )
            except Exception as e:
                logger.warning("Failed to generate next_status: %s", e)

            return RunResult(
                novel_id=novel_id,
                mode=mode,
                chapter_index=chapter_index,
                state_updated=True,
                content=content_text,
                plan=plan,
                usage_metadata=usage,
                next_status=next_status or None,
            )

        raise ValueError(f"Unknown mode: {mode}")

    def preview_input(
        self,
        novel_id: str,
        mode: str,
        user_task: str,
        chapter_index: Optional[int] = None,
        time_slot_override: Optional[str] = None,
        manual_time_slot: bool = False,
        pov_character_ids_override: Optional[list[str]] = None,
        supporting_character_ids: Optional[list[str]] = None,
        lore_tags: Optional[list[str]] = None,
        lore_summary_id: Optional[str] = None,
        timeline_event_focus_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        返回“本次运行将喂给模型的输入”预览，不调用模型、无落盘副作用。
        """
        state = self._load_state_hydrated(novel_id)
        if not state:
            # 兜底：某些热重载瞬间可能导致 hydrated 路径读空，再直接读取一次。
            raw_state = load_state(novel_id)
            if raw_state:
                state = hydrate_state_character_relationships(novel_id, raw_state)
            else:
                raise ValueError(f"novel_id not found: {novel_id}")

        out: Dict[str, Any] = {
            "novel_id": novel_id,
            "mode": mode,
            "manual_time_slot": manual_time_slot,
            "stages": [],
        }

        if (
            mode
            in {
                "plan_only",
                "write_chapter",
                "revise_chapter",
                "expand_chapter",
                "optimize_suggestions",
            }
        ) and (not state.meta.initialized):
            raise ValueError("state not initialized. please run init_state first")

        if mode == "init_state":
            lorebook = self._lorebook(lore_tags, lore_summary_id=lore_summary_id)
            state_context = self._compact_state_for_prompt(state=state, user_task=user_task)
            system, human = build_init_state_prompt(
                user_task=user_task,
                state_context=state_context,
                lorebook=lorebook,
            )
            out["stages"].append({"name": "init_state", "system": system, "human": human})
            return out

        if mode == "optimize_suggestions":
            lorebook = self._lorebook(lore_tags or state.meta.lore_tags, lore_summary_id=lore_summary_id)
            state_context = self._compact_state_for_prompt(
                state=state,
                user_task=user_task,
                novel_id=novel_id,
                timeline_n=4,
                max_chars=10000,
            )
            osys, ohum = build_optimize_suggestions_prompt(
                user_task=user_task,
                state_context=state_context,
                lorebook=lorebook,
            )
            out["stages"].append({"name": "optimize_suggestions", "system": osys, "human": ohum})
            return out

        if chapter_index is None:
            chapter_index = state.meta.current_chapter_index + 1

        strict_no_supporting = bool(pov_character_ids_override) and not bool(supporting_character_ids)
        lorebook = self._lorebook(lore_tags or state.meta.lore_tags, lore_summary_id=lore_summary_id)
        focus_eid = resolve_timeline_focus_event_id(
            novel_id,
            state,
            chapter_index,
            time_slot_override,
            timeline_event_focus_id,
        )
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            time_slot_hint=time_slot_override,
            pov_character_ids_override=pov_character_ids_override,
            supporting_character_ids=supporting_character_ids,
            minimal_context=manual_time_slot,
            strict_no_supporting=strict_no_supporting,
            novel_id=novel_id,
            focus_timeline_event_id=focus_eid,
        )
        continuity_hint = {
            "time_slot_override": time_slot_override,
            "pov_character_ids_override": pov_character_ids_override or [],
            "supporting_character_ids": supporting_character_ids or [],
        }
        plan_system, plan_human = build_plan_chapter_prompt(
            user_task=user_task,
            chapter_index=chapter_index,
            continuity_hint=continuity_hint,
            state_context=state_context,
            lorebook=lorebook,
            strict_no_supporting=strict_no_supporting,
        )
        out["stages"].append({"name": "plan_chapter", "system": plan_system, "human": plan_human})

        if mode in {"write_chapter", "revise_chapter", "expand_chapter"}:
            wm = "expand" if mode == "expand_chapter" else "generate"
            write_system, write_human = build_write_chapter_prompt(
                user_task=user_task,
                state_context=state_context,
                lorebook=lorebook,
                plan=None,
                strict_no_supporting=strict_no_supporting,
                write_mode=wm,
            )
            out["stages"].append({"name": "write_chapter_text", "system": write_system, "human": write_human})

        return out

    def _invoke_json(
        self,
        system: str,
        human: str,
        root_model,
        return_usage: bool = False,
        llm_options: Optional[Dict[str, Any]] = None,
    ):
        """调用模型并解析为 Pydantic；实现见 `agents.novel.structured_invoke.invoke_pydantic_json`。"""
        model = self._model_for_call(llm_options)
        return invoke_pydantic_json(
            model=model,
            system=system,
            human=human,
            root_model=root_model,
            return_usage=return_usage,
            log=logger,
        )
