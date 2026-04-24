"""用户级设置 API（如 DeepSeek API Key）。"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, Literal
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException

from agents.novel.llm_client import resolve_llm_config
from agents.persistence.env_paths import get_lores_root_resolved, get_outputs_root, get_storage_root
from agents.persistence.user_settings import (
    clear_saved_deepseek_api_key,
    get_saved_llm_provider,
    get_saved_openai_compatible_settings,
    save_deepseek_api_key,
    save_llm_provider,
    save_openai_compatible_settings,
)
from webapp.backend.deps import reset_agent_llm_cache
from webapp.backend.schemas import ApiConnectionTestRequest, ApiKeyUpdateRequest, ApiModelListRequest

router = APIRouter(tags=["settings"])

_MODEL_CACHE_TTL_SECONDS = 300
_MODEL_LIST_CACHE: Dict[str, Dict[str, Any]] = {}


def _api_key_fingerprint(key: str) -> str:
    raw = str(key or "").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


def _model_cache_key(*, provider: str, base_url: str, api_key: str) -> str:
    return f"{provider}::{base_url.rstrip('/')}::{_api_key_fingerprint(api_key)}"


def _get_cached_model_list(cache_key: str) -> dict[str, Any] | None:
    row = _MODEL_LIST_CACHE.get(cache_key)
    if not row:
        return None
    exp = float(row.get("expires_at", 0) or 0)
    if exp <= time.time():
        _MODEL_LIST_CACHE.pop(cache_key, None)
        return None
    return row


def _put_cached_model_list(cache_key: str, payload: dict[str, Any]) -> None:
    _MODEL_LIST_CACHE[cache_key] = {
        "expires_at": time.time() + _MODEL_CACHE_TTL_SECONDS,
        "payload": payload,
    }


def _normalize_openai_base_url(raw: str) -> str:
    """
    对齐 Chatbox 常见配置体验：
    - 用户可能只填主机（如 https://xh.v1api.cc）
    - 实际 OpenAI 兼容路径在 /v1
    """
    b = str(raw or "").strip().rstrip("/")
    if not b:
        return b
    sp = urlsplit(b)
    path = (sp.path or "").rstrip("/")
    if path.endswith("/v1") or path.endswith("/v1beta") or path.endswith("/api/v1"):
        return b
    # 没有明显版本路径时，默认补 /v1
    new_path = f"{path}/v1" if path else "/v1"
    return urlunsplit((sp.scheme, sp.netloc, new_path, sp.query, sp.fragment)).rstrip("/")


def _candidate_model_endpoints(base_url: str) -> list[str]:
    """
    兼容不同网关写法，按顺序探测：
    1) {base}/models
    2) {normalized_base}/models
    3) {host}/api/v1/models
    """
    b = str(base_url or "").strip().rstrip("/")
    if not b:
        return []
    out: list[str] = []
    out.append(f"{b}/models")
    nb = _normalize_openai_base_url(b)
    if nb and nb != b:
        out.append(f"{nb}/models")
    sp = urlsplit(b)
    host_only = urlunsplit((sp.scheme, sp.netloc, "", "", "")).rstrip("/")
    if host_only:
        out.append(f"{host_only}/api/v1/models")
    # 保序去重
    uniq: list[str] = []
    seen: set[str] = set()
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        uniq.append(x)
    return uniq


def _infer_model_capabilities(*, model_id: str, model_name: str = "", context_length: int | None = None) -> list[str]:
    text = f"{model_id} {model_name}".lower()
    caps: list[str] = ["chat"]
    if any(k in text for k in ("vision", "vl", "image", "gpt-4o", "omni")):
        caps.append("vision")
    if any(k in text for k in ("tool", "function", "fc", "agent")):
        caps.append("tool")
    if any(k in text for k in ("reason", "thinking", "r1", "o1", "deepseek-reasoner")):
        caps.append("reasoning")
    if isinstance(context_length, int) and context_length >= 128000 and "reasoning" not in caps:
        # 长上下文模型常用于复杂推理，给出轻提示
        caps.append("reasoning")
    # 保序去重
    out: list[str] = []
    seen: set[str] = set()
    for c in caps:
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def _api_key_source() -> Literal["env", "file", "none"]:
    cfg = resolve_llm_config()
    if str(cfg.get("api_key") or "").strip():
        return "file"
    return "none"


@router.get("/settings")
def get_settings():
    cfg = resolve_llm_config()
    saved_provider = get_saved_llm_provider()
    saved_openai = get_saved_openai_compatible_settings()
    return {
        "deepseek_api_key_configured": bool(str(cfg.get("api_key") or "").strip()) and str(cfg.get("provider")) == "deepseek",
        "deepseek_api_key_source": _api_key_source(),
        "llm_provider": saved_provider,
        "llm_provider_effective": str(cfg.get("provider") or saved_provider),
        "llm_source_effective": str(cfg.get("source") or ""),
        "llm_api_key_configured": bool(str(cfg.get("api_key") or "").strip()),
        "openai_compatible_base_url": saved_openai.get("base_url", ""),
        "openai_compatible_model": saved_openai.get("model", ""),
        "storage_root": str(get_storage_root().resolve()),
        "lores_dir": str(get_lores_root_resolved().resolve()),
        "outputs_dir": str(get_outputs_root().resolve()),
    }


@router.post("/settings/api_key")
def post_api_key(body: ApiKeyUpdateRequest):
    provider = str(body.provider or "").strip().lower()
    if provider not in {"deepseek", "openai_compatible"}:
        provider = get_saved_llm_provider()
    save_llm_provider(provider)

    raw = (body.api_key or "").strip()
    if provider == "openai_compatible":
        save_openai_compatible_settings(
            api_key=raw,
            base_url=str(body.base_url or "").strip(),
            model=str(body.model or "").strip(),
        )
    else:
        if raw:
            save_deepseek_api_key(raw)
        else:
            clear_saved_deepseek_api_key()
    reset_agent_llm_cache()
    cfg = resolve_llm_config()
    return {
        "ok": True,
        "deepseek_api_key_source": _api_key_source(),
        "llm_provider_effective": str(cfg.get("provider") or provider),
        "llm_source_effective": str(cfg.get("source") or ""),
    }


def _fetch_openai_compatible_models(*, api_key: str, base_url: str) -> tuple[list[dict[str, Any]], str]:
    endpoints = _candidate_model_endpoints(base_url)
    if not endpoints:
        raise HTTPException(status_code=400, detail="Base URL 不能为空。")

    last_raw = ""
    last_err = ""
    used_endpoint = endpoints[0]
    for endpoint in endpoints:
        used_endpoint = endpoint
        req = urlrequest.Request(
            endpoint,
            method="GET",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlrequest.urlopen(req, timeout=12) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urlerror.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")
            except Exception:
                detail = str(e)
            last_err = f"HTTP {e.code} {detail}"
            continue
        except Exception as e:
            last_err = str(e)
            continue
        last_raw = raw

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # 非 JSON 时尝试下一个候选 endpoint
            continue

        out: list[dict[str, Any]] = []
        if isinstance(data, dict):
            # OpenAI 标准：{ data: [{id: "..."}] }
            rows = data.get("data")
            if isinstance(rows, list):
                for x in rows:
                    if not isinstance(x, dict):
                        continue
                    mid = str(x.get("id") or "").strip()
                    if mid:
                        item: dict[str, Any] = {"id": mid}
                        nm = str(x.get("name") or "").strip()
                        if nm:
                            item["name"] = nm
                        ctx = x.get("context_length")
                        if isinstance(ctx, int) and ctx > 0:
                            item["context_length"] = ctx
                        item["capabilities"] = _infer_model_capabilities(
                            model_id=mid,
                            model_name=nm,
                            context_length=(ctx if isinstance(ctx, int) else None),
                        )
                        out.append(item)
            # 常见网关扩展：{ models: ["a", "b"] } 或 { models: [{id:"a"}] }
            models = data.get("models")
            if isinstance(models, list):
                for x in models:
                    if isinstance(x, str):
                        m = x.strip()
                        if m:
                            out.append(
                                {
                                    "id": m,
                                    "capabilities": _infer_model_capabilities(model_id=m),
                                }
                            )
                    elif isinstance(x, dict):
                        m = str(x.get("id") or x.get("name") or "").strip()
                        if m:
                            item = {"id": m}
                            nm = str(x.get("name") or "").strip()
                            if nm and nm != m:
                                item["name"] = nm
                            ctx = x.get("context_length")
                            if isinstance(ctx, int) and ctx > 0:
                                item["context_length"] = ctx
                            item["capabilities"] = _infer_model_capabilities(
                                model_id=m,
                                model_name=nm,
                                context_length=(ctx if isinstance(ctx, int) else None),
                            )
                            out.append(item)
        elif isinstance(data, list):
            # 宽松兼容：直接返回字符串列表
            for x in data:
                if isinstance(x, str):
                    m = x.strip()
                    if m:
                        out.append(
                            {
                                "id": m,
                                "capabilities": _infer_model_capabilities(model_id=m),
                            }
                        )
                elif isinstance(x, dict):
                    m = str(x.get("id") or x.get("name") or "").strip()
                    if m:
                        item = {"id": m}
                        nm = str(x.get("name") or "").strip()
                        if nm and nm != m:
                            item["name"] = nm
                        ctx = x.get("context_length")
                        if isinstance(ctx, int) and ctx > 0:
                            item["context_length"] = ctx
                        item["capabilities"] = _infer_model_capabilities(
                            model_id=m,
                            model_name=nm,
                            context_length=(ctx if isinstance(ctx, int) else None),
                        )
                        out.append(item)
        by_id: dict[str, dict[str, Any]] = {}
        for it in out:
            mid = str(it.get("id") or "").strip()
            if not mid:
                continue
            prev = by_id.get(mid)
            if not prev:
                by_id[mid] = dict(it)
                continue
            # 合并补充字段，优先保留已有
            if (not prev.get("name")) and it.get("name"):
                prev["name"] = it.get("name")
            if (not prev.get("context_length")) and it.get("context_length"):
                prev["context_length"] = it.get("context_length")
            if it.get("capabilities"):
                caps_old = list(prev.get("capabilities") or [])
                caps_new = list(it.get("capabilities") or [])
                merged_caps: list[str] = []
                seen_caps: set[str] = set()
                for c in [*caps_old, *caps_new]:
                    s = str(c).strip()
                    if not s or s in seen_caps:
                        continue
                    seen_caps.add(s)
                    merged_caps.append(s)
                if merged_caps:
                    prev["capabilities"] = merged_caps
        return [by_id[k] for k in sorted(by_id.keys())], endpoint

    # 所有候选都失败
    snippet = " ".join(last_raw.strip().split())[:240] if last_raw else ""
    if snippet:
        raise HTTPException(
            status_code=400,
            detail=f"模型列表返回不是合法 JSON。请检查 Base URL（已尝试：{', '.join(endpoints)}），响应片段：{snippet}",
        ) from None
    raise HTTPException(
        status_code=400,
        detail=f"模型列表请求失败：{last_err or '未知错误'}（已尝试：{', '.join(endpoints)}）",
    ) from None


def _probe_openai_compatible_chat(
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> None:
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "temperature": 0,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urlrequest.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            _ = resp.read()
    except urlerror.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(e)
        raise HTTPException(status_code=400, detail=f"连通性测试失败：HTTP {e.code} {detail}") from None
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"连通性测试失败：{e}") from None


@router.post("/settings/models")
def list_models(body: ApiModelListRequest):
    provider = str(body.provider or "").strip().lower()
    if provider not in {"deepseek", "openai_compatible"}:
        provider = get_saved_llm_provider()

    key = str(body.api_key or "").strip()
    if not key:
        cfg = resolve_llm_config()
        key = str(cfg.get("api_key") or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="请先填写 API Key。")

    if provider == "deepseek":
        base_url = "https://api.deepseek.com/v1"
    else:
        base_url = str(body.base_url or "").strip()
        if not base_url:
            base_url = get_saved_openai_compatible_settings().get("base_url", "")
        base_url = str(base_url or "").strip()
        if not base_url:
            raise HTTPException(status_code=400, detail="OpenAI 兼容模式请填写 Base URL。")

    normalized_base_url = _normalize_openai_base_url(base_url)
    cache_key = _model_cache_key(provider=provider, base_url=normalized_base_url, api_key=key)
    force_refresh = bool(body.force_refresh)
    cache_hit = False
    payload: dict[str, Any] | None = None
    if not force_refresh:
        cached = _get_cached_model_list(cache_key)
        if cached and isinstance(cached.get("payload"), dict):
            payload = dict(cached.get("payload") or {})
            cache_hit = True

    if payload is None:
        model_items, used_endpoint = _fetch_openai_compatible_models(api_key=key, base_url=base_url)
        models = [str(x.get("id") or "").strip() for x in model_items if str(x.get("id") or "").strip()]
        payload = {
            "provider": provider,
            "base_url": normalized_base_url,
            "used_endpoint": used_endpoint,
            "count": len(models),
            "models": models,
            "model_items": model_items,
            "cache_ttl_seconds": _MODEL_CACHE_TTL_SECONDS,
        }
        _put_cached_model_list(cache_key, payload)

    out = dict(payload)
    out["cache_hit"] = cache_hit
    out["force_refresh"] = force_refresh
    return out


@router.post("/settings/test_connection")
def test_connection(body: ApiConnectionTestRequest):
    provider = str(body.provider or "").strip().lower()
    if provider not in {"deepseek", "openai_compatible"}:
        provider = get_saved_llm_provider()

    key = str(body.api_key or "").strip()
    if not key:
        cfg = resolve_llm_config()
        key = str(cfg.get("api_key") or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="请先填写 API Key。")

    if provider == "deepseek":
        base_url = "https://api.deepseek.com/v1"
        model = str(body.model or "").strip() or "deepseek-chat"
    else:
        base_url = str(body.base_url or "").strip()
        if not base_url:
            base_url = get_saved_openai_compatible_settings().get("base_url", "")
        base_url = str(base_url or "").strip()
        if not base_url:
            raise HTTPException(status_code=400, detail="OpenAI 兼容模式请填写 Base URL。")
        model = str(body.model or "").strip()
        if not model:
            model = get_saved_openai_compatible_settings().get("model", "")
        model = str(model or "").strip()
        if not model:
            raise HTTPException(status_code=400, detail="OpenAI 兼容模式请填写 Model。")

    _probe_openai_compatible_chat(api_key=key, base_url=_normalize_openai_base_url(base_url), model=model)
    return {
        "ok": True,
        "provider": provider,
        "base_url": _normalize_openai_base_url(base_url),
        "model": model,
    }
