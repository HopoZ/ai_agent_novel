from __future__ import annotations

from typing import Any, Dict, Optional

from langchain.messages import HumanMessage, SystemMessage

from agents._internal_marks import z7_module_mark
from agents.lore.lore_summary import (
    build_source_map,
    load_cached_summary,
    save_summary,
    source_hash_from_map,
)
from agents.text_utils import parse_ai_text

_MODULE_REV = z7_module_mark("lr")


def build_lorebook(lore_loader: Any, lore_tags: Optional[list[str]] = None) -> str:
    if lore_tags:
        source = build_source_map(lore_loader, lore_tags)
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

        merged_parts = list(parts)
        for tag in missing_tags:
            md = (source.get(tag, "") or "").strip()
            if md:
                merged_parts.append(f"【{tag}】\n{md}")
        if merged_parts:
            return "### 创作百科全书(混合：摘要+原文) ###\n\n" + "\n\n".join(merged_parts)

    lore = lore_loader.get_all_lore()
    if not lore.strip():
        raise ValueError("settings 目录下没有找到 .md 设定文件，无法生成 lorebook。")
    return lore


def build_lore_summary_llm(
    model: Any, lore_loader: Any, tags: list[str], force: bool = False
) -> Dict[str, Any]:
    tags = [str(t).strip() for t in (tags or []) if str(t).strip()]
    if not tags:
        raise ValueError("tags is required")
    source = build_source_map(lore_loader, tags)
    items: list[str] = []
    tag_summaries: list[Dict[str, str]] = []
    for tag in tags:
        md = source.get(tag, "")
        if not md.strip():
            continue
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
            "要求：压缩，不用人类在意可读性，但对于你读取来说不丢失关键信息（尤其是专有名称）。\n"
            f"原文：\n{md}\n"
        )
        resp = model.invoke([SystemMessage(system), HumanMessage(human)])
        text = parse_ai_text(resp).strip()
        if not text:
            continue
        items.append(f"【{tag}】\n{text}")
        tag_summaries.append({"tag": tag, "summary": text})
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
    src_hash = source_hash_from_map(source)
    return save_summary(
        tags, src_hash, summary_text, mode="llm_manifest_v1", tag_summaries=tag_summaries
    )

