from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any

from langchain.messages import AIMessage


_INVALID_FILENAME_CHARS_RE = re.compile(r'[\\\\/:*?"<>|]+')


def safe_filename(name: str, fallback: str = "novel") -> str:
    name = (name or "").strip()
    if not name:
        return fallback
    name = _INVALID_FILENAME_CHARS_RE.sub("_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:80] if len(name) > 80 else name


def write_outputs_txt(novel_title: str, chapter_index: int, content: str) -> str:
    os.makedirs("outputs", exist_ok=True)
    ts = datetime.now().strftime("%m%d_%H%M%S")
    title = safe_filename(novel_title, fallback="novel")
    # 输出文件名不再使用“第几章”概念（章节可重排/插入），仅用小说名 + 时间戳保证可读与唯一性。
    # chapter_index 仍保留在 storage/chapters/*.json 内部索引里。
    filename = f"{title}_{ts}.txt"
    path = os.path.join("outputs", filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def parse_ai_text(response: AIMessage) -> str:
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


def parse_ai_chunk_text(chunk: Any) -> str:
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

