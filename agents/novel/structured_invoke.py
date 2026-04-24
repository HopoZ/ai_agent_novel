"""
调用 Chat 模型并解析为 Pydantic 模型（含 JSON 修复重试与调试落盘）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, Type, TypeVar, Union

from langchain.messages import HumanMessage, SystemMessage

from agents._internal_marks import z7_module_mark
from agents.persistence.env_paths import get_outputs_root
from agents.text_utils import parse_ai_text

from .llm_json import extract_json_object, json_load_with_retry

logger = logging.getLogger("agents.novel.structured_invoke")
_MODULE_REV = z7_module_mark("si")

T = TypeVar("T")


def parse_streamed_output_to_pydantic(
    raw_text: str,
    model: Any,
    system: str,
    root_model: Type[T],
    *,
    log: Optional[logging.Logger] = None,
) -> T:
    """
    已有模型输出的整段文本（例如流式拼接后）时，按与 invoke_pydantic_json 相同的
    「json_load_with_retry + 第二轮修复」流程解析为 Pydantic。
    """
    log = log or logger
    def llm_fix_invoke(fix_prompt: str) -> str:
        fix_messages = [SystemMessage(system), HumanMessage(fix_prompt)]
        resp = model.invoke(fix_messages)
        return parse_ai_text(resp)

    def parse_fn(json_dict: dict) -> T:
        return root_model.model_validate(json_dict)

    def dump_debug(name: str, text: str) -> Optional[str]:
        try:
            out_dir = get_outputs_root()
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%m%d_%H%M%S")
            path = out_dir / f"debug_json_{name}_{ts}.txt"
            path.write_text(text or "", encoding="utf-8")
            return str(path.resolve())
        except Exception:
            return None

    try:
        data = json_load_with_retry(
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
            logger=log,
        )
        try:
            model_name = getattr(root_model, "__name__", "")
            if isinstance(data, dict):
                if model_name and model_name in data and isinstance(data.get(model_name), dict):
                    data = data[model_name]
                elif len(data) == 1:
                    only_key = next(iter(data.keys()))
                    if isinstance(data.get(only_key), dict) and only_key.lower() in {
                        model_name.lower(),
                        "result",
                        "output",
                    }:
                        data = data[only_key]
        except Exception:
            pass
        return parse_fn(data)
    except Exception as e1:
        log.warning("Streamed JSON parse failed after retry: %s", e1)
        raw_path = dump_debug("raw", raw_text)
        fixed_path: Optional[str] = None
        try:
            fix_prompt2 = (
                "把下面内容修复成合法 JSON：只输出 JSON（单个对象），不要输出任何解释。\n"
                "如果缺失逗号/括号，请补齐；如果有多余文本请删除。\n\n"
                f"{raw_text}\n"
            )
            fixed_text2 = llm_fix_invoke(fix_prompt2)
            fixed_path = dump_debug("fixed", fixed_text2)
            data2 = json.loads(extract_json_object(fixed_text2))
            try:
                model_name = getattr(root_model, "__name__", "")
                if (
                    isinstance(data2, dict)
                    and model_name
                    and model_name in data2
                    and isinstance(data2.get(model_name), dict)
                ):
                    data2 = data2[model_name]
            except Exception:
                pass
            return parse_fn(data2)
        except Exception as e2:
            log.exception("Streamed JSON parse failed hard: %s", e2)
            reason = str(e2).strip().replace("\n", " | ")
            if len(reason) > 280:
                reason = reason[:280] + "..."
            raise ValueError(
                "模型输出 JSON 解析失败（已尝试修复）。"
                + (f" reason={reason}" if reason else "")
                + (f" raw_dump={raw_path}" if raw_path else "")
                + (f" fixed_dump={fixed_path}" if fixed_path else "")
            ) from e2


def invoke_pydantic_json(
    model: Any,
    system: str,
    human: str,
    root_model: Type[T],
    *,
    return_usage: bool = False,
    log: Optional[logging.Logger] = None,
) -> Union[T, Tuple[T, Dict[str, Any]]]:
    """
    调用模型并解析为 Pydantic 模型（带一次“修复 JSON”的重试；失败时再尝试第二轮修复）。
    """
    log = log or logger
    messages = [SystemMessage(system), HumanMessage(human)]

    log.info("Invoking JSON model ...")
    resp = model.invoke(messages)
    raw_text = parse_ai_text(resp)
    usage = getattr(resp, "usage_metadata", None) or {}

    parsed = parse_streamed_output_to_pydantic(raw_text, model, system, root_model, log=log)
    return (parsed, usage) if return_usage else parsed
