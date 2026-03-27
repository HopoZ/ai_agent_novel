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
from langchain.messages import AIMessage, HumanMessage, SystemMessage

from agents.loader import LoreLoader
from agents.lore_summary import (
    build_source_map,
    load_cached_summary,
    save_summary,
    source_hash_from_map,
)
from .state_models import ChapterPlan, ChapterRecord, ContinuityState, CharacterState, CharacterPresence, NovelMeta, NovelState, WorldState
from .storage import (
    get_state_path,
    ensure_novel_dirs,
    list_chapters,
    load_chapter,
    load_state,
    save_chapter,
    save_state,
)


logger = logging.getLogger("novel_agent")

_INVALID_FILENAME_CHARS_RE = re.compile(r'[\\\\/:*?"<>|]+')


def _safe_filename(name: str, fallback: str = "novel") -> str:
    name = (name or "").strip()
    if not name:
        return fallback
    name = _INVALID_FILENAME_CHARS_RE.sub("_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:80] if len(name) > 80 else name


def _write_outputs_txt(novel_title: str, chapter_index: int, content: str) -> str:
    os.makedirs("outputs", exist_ok=True)
    ts = datetime.now().strftime("%m%d_%H%M%S")
    title = _safe_filename(novel_title, fallback="novel")
    # 输出文件名不再使用“第几章”概念（章节可重排/插入），仅用小说名 + 时间戳保证可读与唯一性。
    # chapter_index 仍保留在 storage/chapters/*.json 内部索引里。
    filename = f"{title}_{ts}.txt"
    path = os.path.join("outputs", filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _parse_ai_text(response: AIMessage) -> str:
    """
    LangChain v1 可能返回 content_blocks；把它压成纯文本。
    """
    if isinstance(response.content, str):
        return response.content
    return "".join(
        block.get("text", "")
        for block in (response.content or [])
        if isinstance(block, dict) and block.get("type") == "text"
    )


def _parse_ai_chunk_text(chunk: Any) -> str:
    """
    解析 streaming chunk 为纯文本（兼容 AIMessageChunk / dict blocks）。
    """
    content = getattr(chunk, "content", chunk)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in (content or [])
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content or "")


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
        max_tokens=12000,
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

    def _lorebook(self, lore_tags: Optional[list[str]] = None, lore_summary_id: Optional[str] = None) -> str:
        # 废弃 lore_summary_id：改为按 tags + version（llm_tag_v1）逐 tag 读取缓存
        if lore_tags:
            source = build_source_map(self.lore_loader, lore_tags)
            parts: list[str] = []
            missing_tags: list[str] = []
            for tag in lore_tags:
                md = source.get(tag, "")
                if not md.strip():
                    continue
                tag_src_hash = source_hash_from_map({tag: md})
                hit = load_cached_summary([tag], tag_src_hash, mode="llm_tag_v1")
                if hit:
                    rows = hit.get("tag_summaries") or []
                    if isinstance(rows, list) and rows:
                        first = rows[0] if isinstance(rows[0], dict) else {}
                        summary = str(first.get("summary", "")).strip()
                        if summary:
                            parts.append(f"【{tag}】\n{summary}")
                            continue
                missing_tags.append(tag)

            if parts and (not missing_tags):
                return "### 创作百科全书(LLM摘要版) ###\n\n" + "\n\n".join(parts)

            # 兜底：未命中缓存的 tag 直接注入原文，避免信息缺失
            merged_parts = list(parts)
            for tag in missing_tags:
                md = (source.get(tag, "") or "").strip()
                if md:
                    merged_parts.append(f"【{tag}】\n{md}")
            if merged_parts:
                return "### 创作百科全书(混合：摘要+原文) ###\n\n" + "\n\n".join(merged_parts)

        lore = self.lore_loader.get_all_lore()
        if not lore.strip():
            raise ValueError("settings 目录下没有找到 .md 设定文件，无法生成 lorebook。")
        return lore

    def build_lore_summary_llm(self, tags: list[str], force: bool = False) -> Dict[str, Any]:
        tags = [str(t).strip() for t in (tags or []) if str(t).strip()]
        if not tags:
            raise ValueError("tags is required")
        source = build_source_map(self.lore_loader, tags)
        items: list[str] = []
        tag_summaries: list[Dict[str, str]] = []
        for tag in tags:
            md = source.get(tag, "")
            if not md.strip():
                continue
            # 单 tag 缓存：每个 tag 一份摘要缓存（按 tag + 原文 hash）
            tag_src_hash = source_hash_from_map({tag: md})
            if not force:
                tag_cached = load_cached_summary([tag], tag_src_hash, mode="llm_tag_v1")
                if tag_cached:
                    cached_rows = tag_cached.get("tag_summaries") or []
                    if isinstance(cached_rows, list) and cached_rows:
                        first = cached_rows[0] if isinstance(cached_rows[0], dict) else {}
                        c_tag = str(first.get("tag", "")).strip() or tag
                        c_summary = str(first.get("summary", "")).strip()
                        if c_summary:
                            items.append(f"【{c_tag}】\n{c_summary}")
                            tag_summaries.append({"tag": c_tag, "summary": c_summary})
                            continue

            system = (
                "你是设定压缩器。请对输入内容做极致压缩，但对于后续写作模型不丢失关键信息。"
                "只基于原文，不要新增设定，不要解释过程，只输出摘要正文。"
            )
            human = (
                f"标签：{tag}\n\n"
                "要求：极致压缩，不用在意可读性，但对于你读取来说不丢失关键信息（人物关系、规则边界、触发条件、限制、关键事实）。\n"
                "使用简洁条目输出。\n\n"
                f"原文：\n{md}\n"
            )
            resp = self._get_model().invoke([SystemMessage(system), HumanMessage(human)])
            text = _parse_ai_text(resp).strip()
            if not text:
                continue
            items.append(f"【{tag}】\n{text}")
            tag_summaries.append({"tag": tag, "summary": text})
            # 新生成结果按单 tag 落缓存
            save_summary(
                [tag],
                tag_src_hash,
                f"【{tag}】\n{text}",
                mode="llm_tag_v1",
                tag_summaries=[{"tag": tag, "summary": text}],
            )

        if not items:
            raise ValueError("llm summary build failed: empty result")
        summary_text = "### 创作百科全书(LLM摘要版) ###\n\n" + "\n\n".join(items)
        # 返回当前“选中 tags 组合”的清单对象，便于前端/后续按 summary_id 引用
        src_hash = source_hash_from_map(source)
        return save_summary(tags, src_hash, summary_text, mode="llm_manifest_v1", tag_summaries=tag_summaries)

    def _select_related_character_ids(
        self,
        state: NovelState,
        user_task: str,
        pov_character_ids_override: Optional[list[str]] = None,
        supporting_character_ids: Optional[list[str]] = None,
    ) -> Set[str]:
        ids = {c.character_id for c in (state.characters or []) if c.character_id}
        selected: Set[str] = set()
        for x in (pov_character_ids_override or []):
            if x in ids:
                selected.add(x)
        for x in (supporting_character_ids or []):
            if x in ids:
                selected.add(x)
        for p in (state.continuity.who_is_present or []):
            if p.character_id in ids:
                selected.add(p.character_id)
        task = user_task or ""
        for cid in ids:
            if cid and (cid in task):
                selected.add(cid)
        if not selected and state.continuity.pov_character_id:
            selected.add(state.continuity.pov_character_id)
        return selected

    def _compact_state_for_prompt(
        self,
        state: NovelState,
        user_task: str,
        time_slot_hint: Optional[str] = None,
        pov_character_ids_override: Optional[list[str]] = None,
        supporting_character_ids: Optional[list[str]] = None,
        timeline_n: int = 6,
        max_chars: int = 9000,
    ) -> str:
        rel_ids = self._select_related_character_ids(
            state=state,
            user_task=user_task,
            pov_character_ids_override=pov_character_ids_override,
            supporting_character_ids=supporting_character_ids,
        )
        compact_chars = []
        for c in state.characters or []:
            if rel_ids and c.character_id not in rel_ids:
                continue
            rel = list((c.relationships or {}).items())[:3]
            compact_chars.append(
                {
                    "character_id": c.character_id,
                    "current_location": c.current_location,
                    "relationships": dict(rel),
                    "goals": (c.goals or [])[:2],
                    "known_facts": (c.known_facts or [])[:3],
                }
            )

        # world.key_rules: 按关键词匹配相关规则键；若为空则保底前3项
        task = user_task or ""
        key_rules = state.world.key_rules or {}
        picked_rules: Dict[str, str] = {}
        for k, v in key_rules.items():
            if (k and k in task) or any((cid and cid in (k + v)) for cid in rel_ids):
                picked_rules[k] = v
        if not picked_rules:
            for i, (k, v) in enumerate(key_rules.items()):
                if i >= 3:
                    break
                picked_rules[k] = v

        # timeline：最近N条 + 与 time_slot_hint 相关条
        timeline = list(state.world.timeline or [])
        picked_tl = timeline[-max(1, timeline_n):]
        if time_slot_hint:
            for t in timeline:
                if time_slot_hint in (t.time_slot or "") and t not in picked_tl:
                    picked_tl.append(t)

        payload = {
            "meta": {
                "novel_id": state.meta.novel_id,
                "novel_title": state.meta.novel_title,
                "initialized": state.meta.initialized,
                "current_chapter_index": state.meta.current_chapter_index,
            },
            "continuity": {
                "time_slot": state.continuity.time_slot,
                "pov_character_id": state.continuity.pov_character_id,
                "who_is_present": [p.model_dump() for p in (state.continuity.who_is_present or [])],
            },
            "characters": compact_chars,
            "world": {
                "key_rules": picked_rules,
                "timeline": [t.model_dump(mode="json") for t in picked_tl],
            },
        }
        s = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(s) > max_chars:
            return s[:max_chars] + "\n...[truncated]"
        return s

    def _format_state_for_prompt(self, state: NovelState, max_chars: int = 12000) -> str:
        """
        为了控制上下文长度：只注入“连续性关键字段”的压缩摘要。
        """
        payload = {
            # model_dump(mode="json")：确保 datetime 等类型可以直接被 json.dumps 序列化
            "meta": state.meta.model_dump(mode="json"),
            "continuity": state.continuity.model_dump(),
            "characters": [
                {
                    "character_id": c.character_id,
                    "current_location": c.current_location,
                    "alive": c.alive,
                    "relationships": c.relationships,
                    "goals": c.goals,
                    "known_facts": c.known_facts,
                    "description": c.description,
                }
                for c in state.characters
            ],
            "world": {
                "key_rules": state.world.key_rules,
                "factions": state.world.factions,
                "timeline": [t.model_dump(mode="json") for t in state.world.timeline[-10:]],
                "open_questions": state.world.open_questions[-30:],
            },
            "recent_summaries": state.recent_summaries[-10:],
        }
        s = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(s) > max_chars:
            return s[:max_chars] + "\n...[truncated]"
        return s

    def _neighbor_chapters_context(
        self,
        novel_id: str,
        target_chapter_index: int,
        enabled: bool = True,
    ) -> str:
        """
        仅注入“上下相关两章”（上一章 + 下一章）的轻量摘要，控制输入量。
        """
        if not enabled:
            return "[]"
        chapters = list_chapters(novel_id)
        if not chapters:
            return "[]"
        prev_c = None
        next_c = None
        for c in chapters:
            if c.chapter_index < target_chapter_index:
                if (prev_c is None) or (c.chapter_index > prev_c.chapter_index):
                    prev_c = c
            elif c.chapter_index > target_chapter_index:
                if (next_c is None) or (c.chapter_index < next_c.chapter_index):
                    next_c = c
        selected = [x for x in [prev_c, next_c] if x is not None]
        payload = []
        for c in selected:
            payload.append(
                {
                    "chapter_index": c.chapter_index,
                    "chapter_preset_name": c.chapter_preset_name,
                    "time_slot": c.time_slot,
                    "pov_character_id": c.pov_character_id,
                    "who_is_present": [p.character_id for p in (c.who_is_present or [])],
                    "beats": [
                        {"beat_title": b.beat_title, "summary": b.summary}
                        for b in (c.beats or [])[:6]
                    ],
                }
            )
        return json.dumps(payload, ensure_ascii=False, indent=2)

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
    ) -> Tuple[NovelState, Dict[str, Any]]:
        state = load_state(novel_id)
        if not state:
            raise ValueError(f"novel_id not found: {novel_id}")

        lorebook = self._lorebook(lore_tags, lore_summary_id=lore_summary_id)
        state_context = self._compact_state_for_prompt(state, user_task=user_task)

        system = (
            "你是一个“网文世界建模器”。你的任务是：根据 lorebook 和用户需求，生成完整且可持续的世界状态。"
            "输出必须是严格 JSON，且只包含一个 JSON 对象，不要输出任何多余文本。"
        )
        human = (
            f"用户需求：{user_task}\n\n"
            "当前状态（可能很空）：\n"
            f"{state_context}\n\n"
            "lorebook：\n"
            f"{lorebook}\n\n"
            "请生成“初始化后的 next_state”，要求：\n"
            "- continuity.time_slot 保持用户指定或由你选择的开始时间段\n"
            "- continuity.pov_character_id 选择一个合适的 POV 角色（除非用户已指定）\n"
            "- continuity.who_is_present 至少包含 POV 与核心行动角色\n"
            "- characters 给出主要人物的完整状态（位置/关系/目标/已知事实）\n"
            "- world 给出关键规则结论、阵营/势力概述、时间线与 open_questions\n"
            "- meta.initialized=true，meta.current_chapter_index 保持为 0\n"
            "- recent_summaries 先给一个空列表或 1 条摘要\n"
            "\n输出 JSON 必须符合 NovelState 的结构。"
        )

        plan_json, usage = self._invoke_json(system, human, root_model=NovelState, return_usage=True)
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
    ) -> NovelState:
        state, _ = self._init_state_impl(
            novel_id=novel_id,
            user_task=user_task,
            lore_tags=lore_tags,
            lore_summary_id=lore_summary_id,
        )
        return state

    def init_state_with_usage(
        self,
        novel_id: str,
        user_task: str,
        lore_tags: Optional[list[str]] = None,
        lore_summary_id: Optional[str] = None,
    ) -> Tuple[NovelState, Dict[str, Any]]:
        return self._init_state_impl(
            novel_id=novel_id,
            user_task=user_task,
            lore_tags=lore_tags,
            lore_summary_id=lore_summary_id,
        )

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
    ) -> ChapterPlan:
        state = load_state(novel_id)
        if not state:
            raise ValueError(f"novel_id not found: {novel_id}")
        if not state.meta.initialized:
            raise ValueError("state 尚未初始化。请先用 mode=`init_state` 初始化。")

        lorebook = self._lorebook(lore_tags or state.meta.lore_tags, lore_summary_id=lore_summary_id)
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            time_slot_hint=time_slot_override,
            pov_character_ids_override=pov_character_ids_override,
            supporting_character_ids=supporting_character_ids,
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

        system = (
            "你是一个“网文章节规划器”。你必须输出严格 JSON（只包含一个 JSON 对象），用于生成下一章。"
        )
        human = (
            f"用户本章任务：{user_task}\n\n"
            f"目标 chapter_index：{chapter_index}\n"
            f"连续性提示：{json.dumps(continuity_hint, ensure_ascii=False)}\n\n"
            "当前 NovelState（压缩注入）：\n"
            f"{state_context}\n\n"
            "上下文章节（仅相邻两章；若为空表示本次不注入章节 JSON）：\n"
            f"{chapter_context}\n\n"
            "lorebook（静态设定）：\n"
            f"{lorebook}\n\n"
            "你要输出一个 ChapterPlan：\n"
            "- chapter_index 必须等于目标\n"
            "- time_slot 必须是本章写作的时间段（使用覆盖值或从世界线推断）\n"
            "- pov_character_id：若提供了 pov_character_ids_override，则从该列表中选择最合适的一个作为主 POV；否则自行选择最稳定 POV\n"
            "- who_is_present：列出在本章关键行动中出现的主要角色；若提供 supporting_character_ids，请优先纳入为配角出场候选\n"
            "- beats：提供 6~12 条剧情 beats（每条有 beat_title/summary，可选 time_slot）\n"
            "- next_state：给出“本章结束后的状态补丁（patch）”，不要重复整份 NovelState，避免输出过长被截断：\n"
            "  - 必须包含 meta（沿用 novel_id/novel_title 等）与 continuity（更新到本章结束后的 time_slot/who_is_present/location/POV）\n"
            "  - characters：只需要输出本章涉及/变化的角色（其余角色不必重复输出）\n"
            "  - world：只需要输出本章新增/变化的部分（至少追加 1 条 timeline 事件，summary 简短）\n"
            "  - recent_summaries：可选（0~1 条简短摘要）\n"
            "\n注意：next_state 的 continuity/time_slot 与 who_is_present 要是“本章结束后的状态”。\n"
            "严格要求：只输出 JSON 对象，不要 markdown，不要 ```json 代码块，不要额外解释。"
        )

        return self._invoke_json(system, human, root_model=ChapterPlan)

    @staticmethod
    def merge_state(base: NovelState, patch: NovelState) -> NovelState:
        """
        将模型给出的 next_state（允许是“补丁”）合并到当前 base 状态，避免因输出过长而截断。
        规则（保守合并）：
        - meta：以 patch 为准，但补齐 novel_id/novel_title/lore_tags 等缺失字段
        - continuity：以 patch 为准；缺字段则回退 base
        - characters：若 patch.characters 为空 -> 沿用 base.characters；
          否则按 character_id 合并覆盖（patch 中出现的角色覆盖同 id 的 base）
        - world：若 patch.world 是“空对象” -> 沿用 base.world；
          否则 key_rules/factions/open_questions 用 patch 覆盖非空项；timeline 进行追加（去重按 time_slot+summary）
        - recent_summaries：若 patch.recent_summaries 为空 -> 沿用 base；否则用 patch
        """
        merged = base.model_copy(deep=True)

        # meta（patch 常只给增量；要避免默认值把 base 覆盖坏）
        if patch.meta:
            pm = patch.meta
            mm = merged.meta
            if pm.novel_id:
                mm.novel_id = pm.novel_id
            if pm.novel_title:
                mm.novel_title = pm.novel_title
            if pm.lore_tags:
                mm.lore_tags = pm.lore_tags
            # initialized 一旦为 True，不应被 patch 默认 False 回写
            mm.initialized = bool(mm.initialized or pm.initialized)
            # 章节号只允许前进，不允许因 patch 默认 0 回退
            if isinstance(pm.current_chapter_index, int) and pm.current_chapter_index > mm.current_chapter_index:
                mm.current_chapter_index = pm.current_chapter_index
            merged.meta = mm

        # continuity
        if patch.continuity:
            mc = merged.continuity.model_copy(deep=True)
            pc = patch.continuity
            merged.continuity = ContinuityState(
                time_slot=pc.time_slot or mc.time_slot,
                who_is_present=pc.who_is_present or mc.who_is_present,
                pov_character_id=pc.pov_character_id or mc.pov_character_id,
                current_location=pc.current_location or mc.current_location,
            )

        # characters
        if patch.characters:
            by_id: Dict[str, CharacterState] = {c.character_id: c for c in (base.characters or []) if c.character_id}
            for c in patch.characters:
                if not c.character_id:
                    continue
                by_id[c.character_id] = c
            merged.characters = list(by_id.values())

        # world
        if patch.world:
            pb = patch.world
            mb = merged.world.model_copy(deep=True)
            merged.world = WorldState(
                key_rules=pb.key_rules or mb.key_rules,
                factions=pb.factions or mb.factions,
                timeline=mb.timeline,
                open_questions=pb.open_questions or mb.open_questions,
            )
            # timeline append with simple de-dup
            seen = {(t.time_slot, t.summary) for t in (mb.timeline or [])}
            for t in pb.timeline or []:
                k = (t.time_slot, t.summary)
                if k in seen:
                    continue
                seen.add(k)
                merged.world.timeline.append(t)

        # recent_summaries
        if patch.recent_summaries:
            merged.recent_summaries = patch.recent_summaries

        return merged

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
    ) -> Tuple[str, Dict[str, Any]]:
        state = load_state(novel_id)
        if not state:
            raise ValueError(f"novel_id not found: {novel_id}")

        lorebook = self._lorebook(lore_tags or state.meta.lore_tags, lore_summary_id=lore_summary_id)
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            time_slot_hint=time_slot_hint,
            pov_character_ids_override=pov_character_ids_override,
            supporting_character_ids=supporting_character_ids,
        )
        chapter_context = self._neighbor_chapters_context(
            novel_id=novel_id,
            target_chapter_index=plan.chapter_index,
            enabled=include_chapter_context,
        )

        system = (
            "你是一个网文作家。请根据当前 NovelState 与 ChapterPlan 生成章节正文。"
            "要求：必须严格遵守设定与连续性；不要提及自己是 AI；不要输出任何多余说明。"
            "正文直接开始叙述。"
        )
        human = (
            f"用户本章任务：{user_task}\n\n"
            f"当前状态（压缩）：\n{state_context}\n\n"
            "上下文章节（仅相邻两章；若为空表示本次不注入章节 JSON）：\n"
            f"{chapter_context}\n\n"
            "ChapterPlan（用于写作）：\n"
            f"{plan.model_dump_json(ensure_ascii=False, indent=2)}\n\n"
            "lorebook（静态设定）：\n"
            f"{lorebook}\n\n"
            "请输出纯文本章节正文（不要输出 JSON、不要输出标题前的解释）。"
        )

        messages = [SystemMessage(system), HumanMessage(human)]
        logger.info("Writing chapter %s ...", plan.chapter_index)
        resp = self._get_model().invoke(messages)
        text = _parse_ai_text(resp)
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
    ) -> Iterator[Dict[str, Any]]:
        """
        流式生成章节正文。
        每个 chunk 返回:
        - delta: 文本增量
        - usage_metadata: 可能存在的 token 统计（不同 provider 可能只在末 chunk 提供）
        """
        state = load_state(novel_id)
        if not state:
            raise ValueError(f"novel_id not found: {novel_id}")

        lorebook = self._lorebook(lore_tags or state.meta.lore_tags, lore_summary_id=lore_summary_id)
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            time_slot_hint=time_slot_hint,
            pov_character_ids_override=pov_character_ids_override,
            supporting_character_ids=supporting_character_ids,
        )
        chapter_context = self._neighbor_chapters_context(
            novel_id=novel_id,
            target_chapter_index=plan.chapter_index,
            enabled=include_chapter_context,
        )

        system = (
            "你是一个网文作家。请根据当前 NovelState 与 ChapterPlan 生成章节正文。"
            "要求：必须严格遵守设定与连续性；不要提及自己是 AI；不要输出任何多余说明。"
            "正文直接开始叙述。"
        )
        human = (
            f"用户本章任务：{user_task}\n\n"
            f"当前状态（压缩）：\n{state_context}\n\n"
            "上下文章节（仅相邻两章；若为空表示本次不注入章节 JSON）：\n"
            f"{chapter_context}\n\n"
            "ChapterPlan（用于写作）：\n"
            f"{plan.model_dump_json(ensure_ascii=False, indent=2)}\n\n"
            "lorebook（静态设定）：\n"
            f"{lorebook}\n\n"
            "请输出纯文本章节正文（不要输出 JSON、不要输出标题前的解释）。"
        )

        messages = [SystemMessage(system), HumanMessage(human)]
        logger.info("Streaming write chapter %s ...", plan.chapter_index)
        for chunk in self._get_model().stream(messages):
            text = _parse_ai_chunk_text(chunk)
            usage = getattr(chunk, "usage_metadata", None) or {}
            if text or usage:
                yield {"delta": text, "usage_metadata": usage}

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
    ) -> RunResult:
        state = load_state(novel_id)
        if not state:
            raise ValueError(f"novel_id not found: {novel_id}")

        if mode == "init_state":
            new_state = self.init_state(
                novel_id,
                user_task=user_task,
                lore_tags=lore_tags,
                lore_summary_id=lore_summary_id,
            )
            return RunResult(novel_id=novel_id, mode=mode, chapter_index=None, state_updated=True, content=None)

        if mode in {"plan_only", "write_chapter", "revise_chapter"}:
            if not state.meta.initialized:
                # 无感初始化：当用户直接点“生成正文/规划”等模式时，自动补全初始状态。
                # 用同一个 user_task 作为初始化依据，避免需要用户额外点一次 init_state。
                auto_task = f"（自动初始化）{user_task}".strip()
                logger.info("state not initialized, auto init_state. novel_id=%s mode=%s", novel_id, mode)
                self.init_state(novel_id, user_task=auto_task, lore_tags=lore_tags, lore_summary_id=lore_summary_id)
                state = load_state(novel_id) or state

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
            )
            # 允许 plan.next_state 是“补丁”，这里合并成完整状态再落盘
            try:
                plan.next_state = self.merge_state(state, plan.next_state)
            except Exception as e:
                logger.warning("merge_state failed, fallback to plan.next_state. err=%s", e)

            if mode == "plan_only":
                # 不落正文，但保存 plan 与 next_state（更新状态）
                plan_save_state = plan.next_state
                plan_save_state.meta.current_chapter_index = chapter_index
                plan_save_state.meta.updated_at = datetime.utcnow()
                save_state(novel_id, plan_save_state)

                # 也落盘本章的 beats，便于后续查看/修订
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
                save_chapter(novel_id, record, chapter_preset_name=chapter_preset_name)
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
            save_chapter(novel_id, record, chapter_preset_name=chapter_preset_name)

            # 提交 next_state
            next_state = plan.next_state
            next_state.meta.current_chapter_index = chapter_index
            next_state.meta.updated_at = datetime.utcnow()
            save_state(novel_id, next_state)

            # 同步写出纯文本到 outputs/（保持脚本版的落盘习惯）
            try:
                title = state.meta.novel_title or "未命名小说"
                out_path = _write_outputs_txt(title, chapter_index, content_text)
                logger.info("Wrote outputs txt: %s", out_path)
            except Exception as e:
                logger.warning("Failed to write outputs txt: %s", e)

            return RunResult(
                novel_id=novel_id,
                mode=mode,
                chapter_index=chapter_index,
                state_updated=True,
                content=content_text,
                plan=plan,
                usage_metadata=usage,
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
        state = load_state(novel_id)
        if not state:
            raise ValueError(f"novel_id not found: {novel_id}")

        out: Dict[str, Any] = {
            "novel_id": novel_id,
            "mode": mode,
            "manual_time_slot": manual_time_slot,
            "stages": [],
        }

        # 若会触发自动初始化，则先给出 init_state 输入预览
        if mode in {"plan_only", "write_chapter", "revise_chapter"} and (not state.meta.initialized):
            lorebook_init = self._lorebook(lore_tags, lore_summary_id=lore_summary_id)
            state_context_init = self._compact_state_for_prompt(state=state, user_task=user_task)
            auto_task = f"（自动初始化）{user_task}".strip()
            init_system = (
                "你是一个“网文世界建模器”。你的任务是：根据 lorebook 和用户需求，生成完整且可持续的世界状态。"
                "输出必须是严格 JSON，且只包含一个 JSON 对象，不要输出任何多余文本。"
            )
            init_human = (
                f"用户需求：{auto_task}\n\n"
                "当前状态（可能很空）：\n"
                f"{state_context_init}\n\n"
                "lorebook：\n"
                f"{lorebook_init}\n\n"
                "请生成“初始化后的 next_state”，要求：\n"
                "- continuity.time_slot 保持用户指定或由你选择的开始时间段\n"
                "- continuity.pov_character_id 选择一个合适的 POV 角色（除非用户已指定）\n"
                "- continuity.who_is_present 至少包含 POV 与核心行动角色\n"
                "- characters 给出主要人物的完整状态（位置/关系/目标/已知事实）\n"
                "- world 给出关键规则结论、阵营/势力概述、时间线与 open_questions\n"
                "- meta.initialized=true，meta.current_chapter_index 保持为 0\n"
                "- recent_summaries 先给一个空列表或 1 条摘要\n"
                "\n输出 JSON 必须符合 NovelState 的结构。"
            )
            out["stages"].append({"name": "auto_init", "system": init_system, "human": init_human})

        if mode == "init_state":
            lorebook = self._lorebook(lore_tags, lore_summary_id=lore_summary_id)
            state_context = self._compact_state_for_prompt(state=state, user_task=user_task)
            system = (
                "你是一个“网文世界建模器”。你的任务是：根据 lorebook 和用户需求，生成完整且可持续的世界状态。"
                "输出必须是严格 JSON，且只包含一个 JSON 对象，不要输出任何多余文本。"
            )
            human = (
                f"用户需求：{user_task}\n\n"
                "当前状态（可能很空）：\n"
                f"{state_context}\n\n"
                "lorebook：\n"
                f"{lorebook}\n\n"
                "请生成“初始化后的 next_state”..."
            )
            out["stages"].append({"name": "init_state", "system": system, "human": human})
            return out

        if chapter_index is None:
            chapter_index = state.meta.current_chapter_index + 1

        lorebook = self._lorebook(lore_tags or state.meta.lore_tags, lore_summary_id=lore_summary_id)
        state_context = self._compact_state_for_prompt(
            state=state,
            user_task=user_task,
            time_slot_hint=time_slot_override,
            pov_character_ids_override=pov_character_ids_override,
            supporting_character_ids=supporting_character_ids,
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
        plan_system = "你是一个“网文章节规划器”。你必须输出严格 JSON（只包含一个 JSON 对象），用于生成下一章。"
        plan_human = (
            f"用户本章任务：{user_task}\n\n"
            f"目标 chapter_index：{chapter_index}\n"
            f"连续性提示：{json.dumps(continuity_hint, ensure_ascii=False)}\n\n"
            "当前 NovelState（压缩注入）：\n"
            f"{state_context}\n\n"
            "上下文章节（仅相邻两章；若为空表示本次不注入章节 JSON）：\n"
            f"{chapter_context}\n\n"
            "lorebook（静态设定）：\n"
            f"{lorebook}\n\n"
            "你要输出一个 ChapterPlan（严格 JSON）。"
        )
        out["stages"].append({"name": "plan_chapter", "system": plan_system, "human": plan_human})

        if mode in {"write_chapter", "revise_chapter"}:
            write_system = (
                "你是一个网文作家。请根据当前 NovelState 与 ChapterPlan 生成章节正文。"
                "要求：必须严格遵守设定与连续性；不要提及自己是 AI；不要输出任何多余说明。"
                "正文直接开始叙述。"
            )
            write_human = (
                f"用户本章任务：{user_task}\n\n"
                f"当前状态（压缩）：\n{state_context}\n\n"
                "上下文章节（仅相邻两章；若为空表示本次不注入章节 JSON）：\n"
                f"{chapter_context}\n\n"
                "ChapterPlan（用于写作）：\n"
                "[运行时由上一步 plan_chapter 产出]\n\n"
                "lorebook（静态设定）：\n"
                f"{lorebook}\n\n"
                "请输出纯文本章节正文（不要输出 JSON、不要输出标题前的解释）。"
            )
            out["stages"].append({"name": "write_chapter_text", "system": write_system, "human": write_human})

        return out

    def _invoke_json(self, system: str, human: str, root_model, return_usage: bool = False):
        """
        调用模型并解析为 Pydantic 模型（带一次“修复 JSON”的重试）。
        """
        messages = [SystemMessage(system), HumanMessage(human)]

        def llm_fix_invoke(fix_prompt: str) -> str:
            fix_messages = [SystemMessage(system), HumanMessage(fix_prompt)]
            resp = self._get_model().invoke(fix_messages)
            return _parse_ai_text(resp)

        logger.info("Invoking JSON model ...")
        resp = self._get_model().invoke(messages)
        raw_text = _parse_ai_text(resp)
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

