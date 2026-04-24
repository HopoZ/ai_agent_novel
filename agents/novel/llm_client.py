"""LLM 模型初始化与单次请求参数绑定（DeepSeek + OpenAI 兼容接口）。"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain.chat_models import init_chat_model

from agents._internal_marks import z7_module_mark
from agents.persistence.user_settings import (
    get_saved_deepseek_api_key,
    get_saved_llm_provider,
    get_saved_openai_compatible_settings,
)

logger = logging.getLogger("agents.novel.llm_client")
_MODULE_REV = z7_module_mark("lc")


def resolve_deepseek_api_key() -> str | None:
    """仅从本地 user_settings 读取 DeepSeek API Key。"""
    return get_saved_deepseek_api_key()


def resolve_llm_config() -> Dict[str, str]:
    """
    解析当前有效 LLM 配置（仅本地 user_settings）。
    """
    provider = get_saved_llm_provider()
    if provider == "openai_compatible":
        cfg = get_saved_openai_compatible_settings()
        return {
            "provider": "openai_compatible",
            "api_key": cfg.get("api_key", ""),
            "base_url": cfg.get("base_url", ""),
            "model": cfg.get("model", ""),
            "source": "file_openai",
        }
    return {
        "provider": "deepseek",
        "api_key": get_saved_deepseek_api_key() or "",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "source": "file_deepseek",
    }


def init_deepseek_chat():
    """
    构造默认 Chat 模型（DeepSeek 或 OpenAI 兼容接口）。
    Web 服务可在未调用前不触发，以便无 key 时仍能启动。
    """
    cfg = resolve_llm_config()
    provider = str(cfg.get("provider") or "").strip()
    api_key = str(cfg.get("api_key") or "").strip()
    base_url = str(cfg.get("base_url") or "").strip()
    model_name = str(cfg.get("model") or "").strip()
    if not api_key:
        raise ValueError("未配置 API Key：请在前端「API 密钥」中填写并保存对应提供商配置。")
    if provider == "openai_compatible":
        if not base_url:
            raise ValueError("OpenAI 兼容模式缺少 base_url。")
        if not model_name:
            raise ValueError("OpenAI 兼容模式缺少 model。")
    else:
        base_url = "https://api.deepseek.com/v1"
        model_name = "deepseek-chat"

    return init_chat_model(
        model_name,
        model_provider="openai",
        api_key=api_key,
        base_url=base_url,
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
