"""
设定（Lore）：从 `lores/**/*.md` 加载、摘要缓存、注入运行时。
包结构与职责见 `agents/README.md`。
"""

from .loader import LoreLoader
from .lore_summary import (
    build_source_map,
    get_lore_summary,
    load_cached_summary,
    save_summary,
    source_hash_from_map,
)
from .lore_runtime import (
    build_lorebook,
    build_lore_summary_llm,
    regenerate_auto_lore_with_graph,
)

__all__ = [
    "LoreLoader",
    "build_lorebook",
    "build_lore_summary_llm",
    "regenerate_auto_lore_with_graph",
    "build_source_map",
    "get_lore_summary",
    "load_cached_summary",
    "save_summary",
    "source_hash_from_map",
]
