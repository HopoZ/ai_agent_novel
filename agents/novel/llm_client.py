"""
DeepSeek / LangChain 模型初始化与单次请求参数绑定。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from agents._internal_marks import z7_module_mark

logger = logging.getLogger("agents.novel.llm_client")
_MODULE_REV = z7_module_mark("lc")


def init_deepseek_chat():
    """
    构造默认 DeepSeek Chat 模型（从环境变量读取 DEEPSEEK_API_KEY）。
    Web 服务可在未调用前不触发，以便无 key 时仍能启动。
    """
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


def bind_llm_options(base: Any, llm_options: Optional[Dict[str, Any]] = None) -> Any:
    """
    按单次请求覆盖 sampling 参数（temperature / top_p / max_tokens）。
    未传或全为空时返回 base。
    """
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
