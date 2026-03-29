"""提示词拼装。包结构与职责见 `agents/README.md`。"""

from __future__ import annotations

import json
from typing import Optional

from agents._internal_marks import z7_module_mark
from agents.state.state_models import ChapterPlan

_MODULE_REV = z7_module_mark("pb")


def build_init_state_prompt(user_task: str, state_context: str, lorebook: str) -> tuple[str, str]:
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
    return system, human


def build_plan_chapter_prompt(
    user_task: str,
    chapter_index: int,
    continuity_hint: dict,
    state_context: str,
    lorebook: str,
    strict_no_supporting: bool = False,
) -> tuple[str, str]:
    system = "你是一个“网文章节规划器”。你必须输出严格 JSON（只包含一个 JSON 对象），用于生成本章。"
    human = (
        f"用户本章提示：{user_task}\n\n"
        f"目标 chapter_index：{chapter_index}\n"
        f"连续性提示：{json.dumps(continuity_hint, ensure_ascii=False)}\n\n"
        "当前 NovelState（压缩注入）：\n"
        f"{state_context}\n\n"
        "说明：时序与因果以 world.timeline 及用户任务中的「章节归属/关系图前后事件」为准；"
        "lorebook（静态设定）：\n"
        f"{lorebook}\n\n"
        "你要输出一个 ChapterPlan：\n"
        "- chapter_index 必须等于目标\n"
        "- time_slot 必须是本章写作的时间段（使用覆盖值或从世界线推断）\n"
        "- pov_character_id：若提供了 pov_character_ids_override，则该列表中人物作为主 POV；否则自行选择最稳定 POV\n"
        "- who_is_present：列出在本章关键行动中出现的主要角色；若提供 supporting_character_ids，请优先纳入为配角出场候选\n"
        "- beats：提供 6~12 条剧情 beats（每条有 beat_title/summary，可选 time_slot）\n"
        "- next_state：给出“本章结束后的状态补丁（patch）”，不要重复整份 NovelState，避免输出过长被截断：\n"
        "  - 必须包含 meta（沿用 novel_id/novel_title 等）与 continuity（更新到本章结束后的 time_slot/who_is_present/location/POV）\n"
        "  - characters：只需要输出本章涉及/变化的角色（其余角色不必重复输出）\n"
        "  - world：只需要输出本章新增/变化的部分（可选：0~1 条 timeline 事件，summary 简短）\n"
        "  - 章节与时间线仅通过 time_slot 文本对齐；不要在 world.timeline 里写章号字段\n"
        "  - world.timeline 每个事件对象必须严格包含字段：time_slot（字符串）、summary（字符串），"
        "禁止使用 event_summary、desc、content 等别名\n"
        "  - recent_summaries：可选（0~1 条简短摘要）\n"
        "\n注意：next_state 的 continuity/time_slot 与 who_is_present 要是“本章结束后的状态”。\n"
        "严格要求：只输出 JSON 对象，不要 markdown，不要 ```json 代码块，不要额外解释。"
    )
    if strict_no_supporting:
        human += "\n补充约束：未指定 supporting_character_ids。"
    return system, human


def build_write_chapter_prompt(
    user_task: str,
    state_context: str,
    lorebook: str,
    plan: Optional[ChapterPlan] = None,
    strict_no_supporting: bool = False,
    write_mode: str = "generate",
) -> tuple[str, str]:
    if write_mode == "expand":
        system = (
            "你是一个网文作家。用户在「用户本章提示」中给出了待扩写的短文、梗概或片段。"
            "请结合 NovelState、ChapterPlan 与 lorebook，将其扩写为约 4000～5000 字的连贯章节正文，"
            "不要有 markdown 格式；不要提及自己是 AI；不要输出任何多余说明。"
            "必须保留用户种子的核心情节与人设关系，补足场景、对话、动作与节奏，禁止只稍作润色就结束。"
        )
    else:
        system = (
            "你是一个网文作家。请根据当前 NovelState 与 ChapterPlan 生成章节正文，不要有markdown格式。"
            "要求：必须严格遵守设定与连续性；不要提及自己是 AI；不要输出任何多余说明。"
            "正文直接开始叙述，4000-5000字范围。"
        )
    plan_text = (
        plan.model_dump_json(ensure_ascii=False, indent=2)
        if plan is not None
        else "[运行时由上一步 plan_chapter 产出]"
    )
    human = (
        f"用户本章提示：{user_task}\n\n"
        f"当前状态（压缩）：\n{state_context}\n\n"
        "说明：时序与因果以 world.timeline 及用户任务中的「章节归属/关系图前后事件」为准；"
        "正文写作不额外注入相邻章节的章节 JSON。\n\n"
        "ChapterPlan（用于写作）：\n"
        f"{plan_text}\n\n"
        "lorebook（静态设定）：\n"
        f"{lorebook}\n\n"
        "请输出纯文本章节正文（不要输出 JSON、不要输出标题前的解释）。\n"
        "写作时必须严格遵循 ChapterPlan.time_slot（本章时间段），不要擅自改写本章归属事件。"
    )
    if write_mode == "expand":
        human += (
            "\n\n【扩写硬性要求】以用户本章提示中的片段为叙事骨架展开；"
            "成文长度应达到约 4000～5000 字量级的网文章节体量。"
        )
    if strict_no_supporting:
        human += "\n补充约束：未指定 supporting_character_ids，本章不要主动扩展知名配角出场。"
    return system, human


def build_optimize_suggestions_prompt(
    user_task: str,
    state_context: str,
    lorebook: str,
) -> tuple[str, str]:
    system = (
        "你是资深网文编辑与策划。根据世界观与当前小说状态，针对用户提供的素材或问题给出可执行的优化建议。"
        "不要输出完整重写版正文；以分条建议为主（可含极短示例句）。不要大段 markdown 标题。"
    )
    human = (
        f"用户素材/问题：\n{user_task}\n\n"
        f"当前小说状态（压缩）：\n{state_context}\n\n"
        f"lorebook（静态设定）：\n{lorebook}\n\n"
        "请输出优化建议，要求：\n"
        "- 5～10 条，每条独立成段或一行\n"
        "- 可涉及：情节张力、人设一致、节奏、伏笔、设定贴合、文笔与对话等\n"
        "- 具体可执行，避免空泛套话\n"
    )
    return system, human


def build_next_status_prompt(
    user_task: str,
    chapter_index: int,
    state_context: str,
    latest_content: str,
) -> tuple[str, str]:
    system = (
        "你是网文策划编辑。你要为作者输出“下一章走向建议（next_status）”。"
        "这段建议只给作者参考，不参与当前章节生成。"
    )
    human = (
        f"本章任务：{user_task}\n"
        f"当前章节索引：{chapter_index}\n\n"
        "当前状态（压缩）：\n"
        f"{state_context}\n\n"
        "本章正文（用于把握收束点）：\n"
        f"{latest_content}\n\n"
        "请输出 next_status（纯文本），要求：\n"
        "- 充满想象力，有爽点，有结构化设计\n"
        "- 给出 3~5 条“下章方向建议”\n"
        "- 每条都包含：冲突核心 + 爽点爆发 + 章节收尾钩子\n"
        "- 不要复述本章，不要输出 JSON，不要代码块\n"
    )
    return system, human
