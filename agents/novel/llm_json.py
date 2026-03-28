"""
从模型输出中抽取 JSON 对象，并在解析失败时用 LLM 再修一次。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Callable, Optional

from agents._internal_marks import z7_module_mark

_MODULE_REV = z7_module_mark("lj")


def extract_json_object(text: str) -> str:
    """
    从一段可能带多余内容的文本里，提取第一个 {...} 作为 JSON。
    """
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if fenced:
        return fenced.group(1)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output.")
    return text[start : end + 1]


def json_load_with_retry(
    raw_text: str,
    fix_prompt: str,
    llm_invoke_fn: Callable[[str], str],
    *,
    logger: Optional[logging.Logger] = None,
) -> dict:
    """
    将模型输出 JSON 解析失败时，进行一次“修复 JSON”的重试。
    """
    log = logger or logging.getLogger(__name__)
    try:
        candidate = extract_json_object(raw_text)
        return json.loads(candidate)
    except Exception as e:
        log.warning("JSON parse failed, retrying. err=%s", e)
        fixed_text = llm_invoke_fn(fix_prompt)
        candidate = extract_json_object(fixed_text)
        return json.loads(candidate)
