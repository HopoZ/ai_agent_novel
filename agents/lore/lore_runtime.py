from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

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
        raise ValueError("lores 目录下没有找到 .md 设定文件，无法生成 lorebook。")
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


def _extract_first_json_object(text: str) -> Dict[str, Any]:
    s = str(text or "").strip()
    if not s:
        raise ValueError("empty llm response")
    try:
        data = json.loads(s)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    l = s.find("{")
    r = s.rfind("}")
    if l < 0 or r < 0 or r <= l:
        raise ValueError("llm response does not contain json object")
    chunk = s[l : r + 1]
    data = json.loads(chunk)
    if not isinstance(data, dict):
        raise ValueError("llm response json root must be object")
    return data


def regenerate_auto_lore_with_graph(
    *,
    model: Any,
    novel_id: str,
    novel_title: str,
    brief: str,
    old_docs: List[Dict[str, str]],
    state_payload: Dict[str, Any],
    graph_payload: Dict[str, Any],
    target_filenames: List[str],
) -> List[Dict[str, str]]:
    """
    图谱引导的自动设定整包重写（4文件）。
    返回: [{"filename": "...md", "content": "..."}]
    """
    if not target_filenames:
        raise ValueError("target_filenames is required")
    old_docs_json = json.dumps(old_docs or [], ensure_ascii=False, indent=2)
    state_json = json.dumps(state_payload or {}, ensure_ascii=False, indent=2)
    graph_json = json.dumps(graph_payload or {}, ensure_ascii=False, indent=2)
    target_json = json.dumps(target_filenames, ensure_ascii=False)

    system = (
        "你是小说自动设定重写器。"
        "你必须只输出一个 JSON 对象，不要输出任何额外文本。"
        "输出格式固定为："
        '{"files":[{"filename":"00_项目说明.md","content":"..."}, ...]}。'
    )
    human = (
        f"任务：为小说《{novel_title or '未命名小说'}》重写自动设定文件。\n"
        f"- 小说ID：{novel_id}\n"
        f"- 目标文件名（必须一一对应，且仅这些）：{target_json}\n"
        f"- 作者补充意图：{brief or '无'}\n\n"
        "要求：\n"
        "1) 以现有自动设定文件为参考，但允许整包重写。\n"
        "2) 必须与当前图谱/状态保持一致：人物、关系、时间线事件、章节归属不应冲突。\n"
        "3) 输出 content 必须为可读 Markdown，且每个文件内容非空。\n"
        "4) 不得新增目标文件名之外的文件。\n"
        "5) 若信息不足，可保留待补充占位，但不能编造明显冲突事实。\n\n"
        f"现有自动设定文件：\n{old_docs_json}\n\n"
        f"当前状态（state）：\n{state_json}\n\n"
        f"当前图谱（graph）：\n{graph_json}\n"
    )
    resp = model.invoke([SystemMessage(system), HumanMessage(human)])
    raw = parse_ai_text(resp)
    data = _extract_first_json_object(raw)
    rows = data.get("files")
    if not isinstance(rows, list):
        raise ValueError("llm output missing files[]")

    need = [str(x or "").strip() for x in target_filenames if str(x or "").strip()]
    need_set = set(need)
    got_map: Dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        fn = str(row.get("filename") or "").strip()
        content = str(row.get("content") or "").strip()
        if (not fn) or (fn not in need_set) or (not content):
            continue
        got_map[fn] = content

    miss = [x for x in need if x not in got_map]
    if miss:
        raise ValueError(f"llm output missing target files: {miss}")
    return [{"filename": fn, "content": got_map[fn]} for fn in need]

