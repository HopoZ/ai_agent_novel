from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterator, Optional, Set, Tuple, Type

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, SystemMessage

from agents._internal_marks import z7_module_mark
from agents.loader import LoreLoader
from agents.lore_runtime import build_lore_summary_llm as build_lore_summary_llm_runtime
from agents.lore_runtime import build_lorebook
from agents.prompt_builders import (
    build_init_state_prompt,
    build_next_status_prompt,
    build_plan_chapter_prompt,
    build_write_chapter_prompt,
)
from agents.state_compactor import (
    compact_state_for_prompt as compact_state_for_prompt_runtime,
    format_state_for_prompt as format_state_for_prompt_runtime,
    select_related_character_ids as select_related_character_ids_runtime,
)
from agents.state_merge import (
    merge_state as merge_state_runtime,
    neighbor_chapters_context as neighbor_chapters_context_runtime,
)
from agents.text_utils import parse_ai_chunk_text, parse_ai_text, write_outputs_txt
from agents.graph_tables import hydrate_state_character_relationships, persist_chapter_artifacts
from .state_models import ChapterPlan, ChapterRecord, ContinuityState, NovelMeta, NovelState
from .storage import (
    ensure_novel_dirs,
    load_state,
    save_state,
)


logger = logging.getLogger("novel_agent")
_MODULE_REV = z7_module_mark("na")


def _extract_json_object(text: str) -> str:
    """
    从一段可能带多余内容的文本里，提取第一个 {...} 作为 JSON。
    """
    # 优先找代码块里的 JSON
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if fenced:
        return fenced.group(1)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output.")
    return text[start : end + 1]


def _json_load_with_retry(raw_text: str, fix_prompt: str, llm_invoke_fn) -> dict:
    """
    将模型输出 JSON 解析失败时，进行一次“修复 JSON”的重试。
    """
    try:
        candidate = _extract_json_object(raw_text)
        return json.loads(candidate)
    except Exception as e:
        logger.warning("JSON parse failed, retrying. err=%s", e)
        fixed_res = llm_invoke_fn(fix_prompt)
        fixed_text = fixed_res
        candidate = _extract_json_object(fixed_text)
        return json.loads(candidate)


def _init_llm():
    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("请在 .env 文件中添加 DEEPSEEK_API_KEY")

    return init_chat_model(
        "deepseek-chat",
        model_provider="openai",
        api_key=api_key,
        base_url="https://api.deepseek.com/v1",
        temperature=0.7,
        output_version="v1",
        max_tokens=20000,
    )


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

    def __init__(self, lore_path: str = "settings"):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        self.lore_loader = LoreLoader(data_path=lore_path)
        self.model = None  # 懒加载：避免未配置 key 时无法启动 Web

    def _get_model(self):
        if self.model is None:
            self.model = _init_llm()
        return self.model

    def _model_for_call(self, llm_options: Optional[Dict[str, Any]] = None):
        """
        按单次请求覆盖 sampling 参数（temperature / top_p / max_tokens）。
        未传或全为空时使用全局默认模型配置。
        """
        base = self._get_model()
        if not llm_options:
            return base
        kwargs: Dict[str, Any] = {}
        for key in ("temperature", "top_p", "max_tokens"):
            v = llm_options.get(key)
            if v is not None:
                kwargs[key] = v
        if not kwargs:
            return base
        bind = getattr(base, "bind", None)
        if callable(bind):
            try:
                return bind(**kwargs)
            except Exception as e:
                logger.warning("model.bind(%s) failed, using base model: %s", kwargs, e)
        return base

    def _load_state_hydrated(self, novel_id: str) -> Optional[NovelState]:
        state = load_state(novel_id)
        if not state:
            return None
        return hydrate_state_character_relationships(novel_id, state)

    def _lorebook(self, lore_tags: Optional[list[str]] = None, lore_summary_id: Optional[str] = None) -> str:
        # lore_summary_id 已废弃；按 tags + 单 tag 缓存读取 lorebook
        return build_lorebook(self.lore_loader, lore_tags=lore_tags)

    def _pick_lore_tags_for_strict_mode(
        self,
        lore_tags: Optional[list[str]],
        pov_character_ids_override: Optional[list[str]],
        strict_no_supporting: bool,
    ) -> Optional[list[str]]:
        if (not strict_no_supporting) or (not lore_tags):
            return lore_tags
        povs = [str(x).strip() for x in (pov_character_ids_override or []) if str(x).strip()]
        if not povs:
            return lore_tags
        picked: list[str] = []
        for tag in lore_tags:
            t = str(tag or "")
            if any(pov in t for pov in povs):
                picked.append(t)
        return picked or lore_tags

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
        )

    def _format_state_for_prompt(self, state: NovelState, max_chars: int = 12000) -> str:
        return format_state_for_prompt_runtime(state=state, max_chars=max_chars)

    def _neighbor_chapters_context(
        self,
        novel_id: str,
        target_chapter_index: int,
        enabled: bool = True,
    ) -> str:
        return neighbor_chapters_context_runtime(
            novel_id=novel_id,
            target_chapter_index=target_chapter_index,
            enabled=enabled,
        )

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
                current_location=None,
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
        data = json.loads(_extract_json_object(raw_text))
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
        include_chapter_context: bool = True,
        lore_tags: Optional[list[str]] = None,
        lore_summary_id: Optional[str] = None,
        llm_options: Optional[Dict[str, Any]] = None,
    ) -> ChapterPlan:
        state = self._load_state_hydrated(novel_id)
        if not state:
            raise ValueError(f"novel_id not found: {novel_id}")
        if not state.meta.initialized:
            raise ValueError("state 尚未初始化。请先用 mode=`init_state` 初始化。")

        strict_no_supporting = bool(pov_character_ids_override) and not bool(supporting_character_ids)
        picked_lore_tags = self._pick_lore_tags_for_strict_mode(
            lore_tags=(lore_tags or state.meta.lore_tags),
            pov_character_ids_override=pov_character_ids_override,
            strict_no_supporting=strict_no_supporting,
        )
        lorebook = self._lorebook(picked_lore_tags, lore_summary_id=lore_summary_id)
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            time_slot_hint=time_slot_override,
            pov_character_ids_override=pov_character_ids_override,
            supporting_character_ids=supporting_character_ids,
            minimal_context=(not include_chapter_context),
            strict_no_supporting=strict_no_supporting,
        )
        chapter_context = self._neighbor_chapters_context(
            novel_id=novel_id,
            target_chapter_index=chapter_index,
            enabled=include_chapter_context,
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
            chapter_context=chapter_context,
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
        include_chapter_context: bool = True,
        lore_tags: Optional[list[str]] = None,
        lore_summary_id: Optional[str] = None,
        llm_options: Optional[Dict[str, Any]] = None,
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
        picked_lore_tags = self._pick_lore_tags_for_strict_mode(
            lore_tags=(lore_tags or state.meta.lore_tags),
            pov_character_ids_override=pov_character_ids_override,
            strict_no_supporting=strict_no_supporting,
        )
        lorebook = self._lorebook(picked_lore_tags, lore_summary_id=lore_summary_id)
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            time_slot_hint=time_slot_override,
            pov_character_ids_override=pov_character_ids_override,
            supporting_character_ids=supporting_character_ids,
            minimal_context=(not include_chapter_context),
            strict_no_supporting=strict_no_supporting,
        )
        chapter_context = self._neighbor_chapters_context(
            novel_id=novel_id,
            target_chapter_index=chapter_index,
            enabled=include_chapter_context,
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
            chapter_context=chapter_context,
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

        data = _json_load_with_retry(
            raw_text=raw_text,
            fix_prompt=(
                "你输出的不是合法 JSON。请仅输出一个合法 JSON 对象，内容与原意一致，"
                "并确保结构符合 ChapterPlan（不要输出任何额外文本）。\n\n"
                "原始输出：\n"
                f"{raw_text}\n"
            ),
            llm_invoke_fn=llm_fix_invoke,
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
        include_chapter_context: bool = True,
        lore_tags: Optional[list[str]] = None,
        lore_summary_id: Optional[str] = None,
        time_slot_hint: Optional[str] = None,
        pov_character_ids_override: Optional[list[str]] = None,
        supporting_character_ids: Optional[list[str]] = None,
        llm_options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        state = self._load_state_hydrated(novel_id)
        if not state:
            raise ValueError(f"novel_id not found: {novel_id}")

        strict_no_supporting = bool(pov_character_ids_override) and not bool(supporting_character_ids)
        picked_lore_tags = self._pick_lore_tags_for_strict_mode(
            lore_tags=(lore_tags or state.meta.lore_tags),
            pov_character_ids_override=pov_character_ids_override,
            strict_no_supporting=strict_no_supporting,
        )
        lorebook = self._lorebook(picked_lore_tags, lore_summary_id=lore_summary_id)
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            time_slot_hint=time_slot_hint,
            pov_character_ids_override=pov_character_ids_override,
            supporting_character_ids=supporting_character_ids,
            minimal_context=(not include_chapter_context),
            strict_no_supporting=strict_no_supporting,
        )
        chapter_context = self._neighbor_chapters_context(
            novel_id=novel_id,
            target_chapter_index=plan.chapter_index,
            enabled=include_chapter_context,
        )

        system, human = build_write_chapter_prompt(
            user_task=user_task,
            state_context=state_context,
            chapter_context=chapter_context,
            lorebook=lorebook,
            plan=plan,
            strict_no_supporting=strict_no_supporting,
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
        include_chapter_context: bool = True,
        lore_tags: Optional[list[str]] = None,
        lore_summary_id: Optional[str] = None,
        time_slot_hint: Optional[str] = None,
        pov_character_ids_override: Optional[list[str]] = None,
        supporting_character_ids: Optional[list[str]] = None,
        llm_options: Optional[Dict[str, Any]] = None,
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
        picked_lore_tags = self._pick_lore_tags_for_strict_mode(
            lore_tags=(lore_tags or state.meta.lore_tags),
            pov_character_ids_override=pov_character_ids_override,
            strict_no_supporting=strict_no_supporting,
        )
        lorebook = self._lorebook(picked_lore_tags, lore_summary_id=lore_summary_id)
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            time_slot_hint=time_slot_hint,
            pov_character_ids_override=pov_character_ids_override,
            supporting_character_ids=supporting_character_ids,
            minimal_context=(not include_chapter_context),
            strict_no_supporting=strict_no_supporting,
        )
        chapter_context = self._neighbor_chapters_context(
            novel_id=novel_id,
            target_chapter_index=plan.chapter_index,
            enabled=include_chapter_context,
        )

        system, human = build_write_chapter_prompt(
            user_task=user_task,
            state_context=state_context,
            chapter_context=chapter_context,
            lorebook=lorebook,
            plan=plan,
            strict_no_supporting=strict_no_supporting,
        )

        messages = [SystemMessage(system), HumanMessage(human)]
        logger.info("Streaming write chapter %s ...", plan.chapter_index)
        model = self._model_for_call(llm_options)
        for chunk in model.stream(messages):
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
    ) -> str:
        """
        独立生成“下章建议”，不参与当前章节 plan/write。
        """
        state = self._load_state_hydrated(novel_id)
        if not state:
            return ""
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            time_slot_hint=state.continuity.time_slot,
            timeline_n=4,
            max_chars=7000,
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

        if mode in {"plan_only", "write_chapter", "revise_chapter"}:
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
                include_chapter_context=(not manual_time_slot),
                lore_tags=lore_tags,
                lore_summary_id=lore_summary_id,
                llm_options=llm_options,
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

            # write_chapter / revise_chapter：先写正文，再落盘章节
            content_text, usage = self.write_chapter_text(
                novel_id=novel_id,
                plan=plan,
                user_task=user_task,
                include_chapter_context=(not manual_time_slot),
                lore_tags=lore_tags,
                lore_summary_id=lore_summary_id,
                time_slot_hint=time_slot_override,
                pov_character_ids_override=pov_character_ids_override,
                supporting_character_ids=supporting_character_ids,
                llm_options=llm_options,
            )

            if mode == "revise_chapter":
                # revise 仍以 plan 的 next_state 为准
                pass

            record = ChapterRecord(
                chapter_index=chapter_index,
                chapter_preset_name=chapter_preset_name,
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

        if mode in {"plan_only", "write_chapter", "revise_chapter"} and (not state.meta.initialized):
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

        if chapter_index is None:
            chapter_index = state.meta.current_chapter_index + 1

        strict_no_supporting = bool(pov_character_ids_override) and not bool(supporting_character_ids)
        picked_lore_tags = self._pick_lore_tags_for_strict_mode(
            lore_tags=(lore_tags or state.meta.lore_tags),
            pov_character_ids_override=pov_character_ids_override,
            strict_no_supporting=strict_no_supporting,
        )
        lorebook = self._lorebook(picked_lore_tags, lore_summary_id=lore_summary_id)
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            time_slot_hint=time_slot_override,
            pov_character_ids_override=pov_character_ids_override,
            supporting_character_ids=supporting_character_ids,
            minimal_context=manual_time_slot,
            strict_no_supporting=strict_no_supporting,
        )
        chapter_context = self._neighbor_chapters_context(
            novel_id=novel_id,
            target_chapter_index=chapter_index,
            enabled=(not manual_time_slot),
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
            chapter_context=chapter_context,
            lorebook=lorebook,
            strict_no_supporting=strict_no_supporting,
        )
        out["stages"].append({"name": "plan_chapter", "system": plan_system, "human": plan_human})

        if mode in {"write_chapter", "revise_chapter"}:
            write_system, write_human = build_write_chapter_prompt(
                user_task=user_task,
                state_context=state_context,
                chapter_context=chapter_context,
                lorebook=lorebook,
                plan=None,
                strict_no_supporting=strict_no_supporting,
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
        """
        调用模型并解析为 Pydantic 模型（带一次“修复 JSON”的重试）。
        """
        messages = [SystemMessage(system), HumanMessage(human)]
        model = self._model_for_call(llm_options)

        def llm_fix_invoke(fix_prompt: str) -> str:
            fix_messages = [SystemMessage(system), HumanMessage(fix_prompt)]
            resp = model.invoke(fix_messages)
            return parse_ai_text(resp)

        logger.info("Invoking JSON model ...")
        resp = model.invoke(messages)
        raw_text = parse_ai_text(resp)
        usage = getattr(resp, "usage_metadata", None) or {}

        def parse_fn(json_dict: dict):
            return root_model.model_validate(json_dict)

        def dump_debug(name: str, text: str) -> Optional[str]:
            try:
                os.makedirs("outputs", exist_ok=True)
                ts = datetime.now().strftime("%m%d_%H%M%S")
                path = os.path.join("outputs", f"debug_json_{name}_{ts}.txt")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text or "")
                return path
            except Exception:
                return None

        # 解析 + 自动修复（两次策略）
        try:
            data = _json_load_with_retry(
                raw_text=raw_text,
                fix_prompt=(
                    "你输出的不是合法 JSON。请仅输出一个合法 JSON 对象，内容与原意一致，"
                    "并确保结构符合需要的模型（不要输出任何额外文本）。\n\n"
                    "要求：\n"
                    "- 只输出一个 JSON 对象\n"
                    "- 不要使用中文引号\n"
                    "- 所有字符串必须用英文双引号\n"
                    "- 不要包含任何注释\n\n"
                    f"原始输出：\n{raw_text}\n"
                ),
                llm_invoke_fn=llm_fix_invoke,
            )
            # 兼容模型额外包了一层 {"ChapterPlan": {...}} 之类的情况
            try:
                model_name = getattr(root_model, "__name__", "")
                if isinstance(data, dict):
                    if model_name and model_name in data and isinstance(data.get(model_name), dict):
                        data = data[model_name]
                    elif len(data) == 1:
                        only_key = next(iter(data.keys()))
                        if isinstance(data.get(only_key), dict) and only_key.lower() in {model_name.lower(), "result", "output"}:
                            data = data[only_key]
            except Exception:
                pass
            parsed = parse_fn(data)
            return (parsed, usage) if return_usage else parsed
        except Exception as e1:
            logger.warning("Root JSON parse failed after retry: %s", e1)
            raw_path = dump_debug("raw", raw_text)
            try:
                fix_prompt2 = (
                    "把下面内容修复成合法 JSON：只输出 JSON（单个对象），不要输出任何解释。\n"
                    "如果缺失逗号/括号，请补齐；如果有多余文本请删除。\n\n"
                    f"{raw_text}\n"
                )
                fixed_text2 = llm_fix_invoke(fix_prompt2)
                fixed_path = dump_debug("fixed", fixed_text2)
                data2 = json.loads(_extract_json_object(fixed_text2))
                try:
                    model_name = getattr(root_model, "__name__", "")
                    if isinstance(data2, dict) and model_name and model_name in data2 and isinstance(data2.get(model_name), dict):
                        data2 = data2[model_name]
                except Exception:
                    pass
                parsed2 = parse_fn(data2)
                return (parsed2, usage) if return_usage else parsed2
            except Exception as e2:
                logger.exception("Root JSON parse failed hard: %s", e2)
                raise ValueError(
                    "模型输出 JSON 解析失败（已尝试修复）。"
                    + (f" raw_dump={raw_path}" if raw_path else "")
                    + (f" fixed_dump={fixed_path}" if 'fixed_path' in locals() and fixed_path else "")
                )

