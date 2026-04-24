# 负责加载设定文件并构建创作百科全书的上下文信息

import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from agents.persistence.env_paths import get_storage_root, try_get_lores_dir_from_env


class LoreLoader:
    def __init__(self, data_path="lores"):
        o = try_get_lores_dir_from_env()
        if o is not None:
            self.data_path = o
            return
        # 与 NOVEL_AGENT_STORAGE_DIR 为同一应用数据根时，lores 落在其下 lores/（Electron 安装版）
        if os.environ.get("NOVEL_AGENT_STORAGE_DIR", "").strip():
            self.data_path = get_storage_root() / "lores"
            return
        # 开发 / 源码：相对路径固定到仓库根（agents/lore/loader.py -> 向上两级）
        repo_root = Path(__file__).resolve().parents[2]
        p = Path(data_path)
        self.data_path = p if p.is_absolute() else (repo_root / p)

    @staticmethod
    def _is_ignored_markdown(file_path: Path) -> bool:
        """
        忽略目录说明类文档，避免被当作 lore tag。
        """
        return file_path.stem.lower() == "readme"

    def _scan_markdown_files(self) -> list[Path]:
        """
        递归扫描 lores/**/*.md（忽略 README.md），返回相对路径排序列表。
        """
        if not self.data_path.exists():
            return []
        files = [
            p
            for p in self.data_path.rglob("*.md")
            if p.is_file() and (not self._is_ignored_markdown(p))
        ]
        files.sort(key=lambda x: x.relative_to(self.data_path).as_posix())
        return files

    def _path_to_tag(self, file_path: Path) -> str:
        """
        将 markdown 文件路径映射为 tag（目录结构可见）：
        lores/world/faction.md -> world/faction
        """
        rel = file_path.relative_to(self.data_path)
        return rel.with_suffix("").as_posix()

    def _resolve_tag_to_path(self, tag: str) -> Path | None:
        """
        支持两种 tag 解析：
        1) 新格式：带目录的相对路径 tag（如 world/faction）
        2) 兼容旧格式：仅文件名（如 faction），若同名冲突取第一个并按扫描顺序稳定
        """
        if not tag:
            return None
        clean = str(tag).strip().replace("\\", "/")
        if not clean:
            return None

        # 新格式优先：按相对路径精确匹配
        direct = self.data_path / f"{clean}.md"
        if direct.exists() and direct.is_file():
            return direct

        # 兼容旧格式：按 basename 匹配
        base = clean.split("/")[-1]
        for p in self._scan_markdown_files():
            if p.stem == base:
                return p
        return None

    def get_lore_tags(self):
        """
        返回 lores/**/*.md 的标签（保留目录层级）。
        例如：世界观/势力/联盟
        """
        return [self._path_to_tag(p) for p in self._scan_markdown_files()]

    def get_lore_tag_groups(self) -> dict[str, list[str]]:
        """
        按目录分组返回标签。
        - 根目录文件分组名：根目录
        - 子目录文件分组名：目录路径（如 世界观/势力）
        """
        groups: Dict[str, List[str]] = {}
        for p in self._scan_markdown_files():
            rel = p.relative_to(self.data_path)
            group = rel.parent.as_posix() if rel.parent.as_posix() not in {".", ""} else "根目录"
            tag = self._path_to_tag(p)
            groups.setdefault(group, []).append(tag)
        # 保持组内 tag 稳定排序
        for k in list(groups.keys()):
            groups[k].sort()
        return dict(sorted(groups.items(), key=lambda x: x[0]))

    def get_lore_by_tags(self, tags: list[str]) -> str:
        """
        读取指定 tags 对应的 markdown，并拼成 lorebook 文本块。
        """
        if not self.data_path.exists():
            return ""
        want = {str(t).strip() for t in (tags or []) if str(t).strip()}
        full_context = "### 创作百科全书 (Lorebook) ###\n"
        # 为稳定性按相对路径排序输出
        for tag in self.get_lore_tags():
            if tag not in want:
                continue
            file_path = self._resolve_tag_to_path(tag)
            if not file_path:
                continue
            with open(file_path, "r", encoding="utf-8") as f:
                full_context += f"\n【{tag}】:\n{f.read()}\n"
        return full_context

    def get_markdown_by_tag(self, tag: str) -> str:
        """
        读取单个 tag 对应的 markdown 内容（支持目录结构）。
        """
        file_path = self._resolve_tag_to_path(tag)
        if not file_path:
            return ""
        return file_path.read_text(encoding="utf-8")

    def get_preview_by_tag(self, tag: str, max_chars: int = 0) -> str:
        """
        返回 tag 对应设定的预览文本（用于前端悬浮提示）。
        """
        md = self.get_markdown_by_tag(tag)
        md = md.strip()
        if not md:
            return ""
        # max_chars <= 0 代表不截断，让前端用滚动容器显示
        if max_chars and max_chars > 0 and len(md) > max_chars:
            return md[:max_chars]
        return md

    def get_all_lore(self):
        """扫描目录并读取所有设定文件"""
        return self.get_lore_by_tags(self.get_lore_tags())

    @staticmethod
    def _extract_query_terms(query: str) -> list[str]:
        """
        近似 grep 的关键词切分：
        - 先按中英文常见分隔符切词
        - 保留长度 >= 2 的词，去重且保序
        """
        raw = [p.strip() for p in re.split(r"[\s,，。！？、;；:：()（）\[\]{}<>\"'`]+", str(query or "")) if p.strip()]
        terms: list[str] = []
        seen: set[str] = set()
        for t in raw:
            if len(t) < 2:
                continue
            if t in seen:
                continue
            seen.add(t)
            terms.append(t)
        return terms

    @staticmethod
    def _best_snippet(md: str, terms: list[str], max_lines: int = 10) -> str:
        if not md.strip():
            return ""
        lines = md.splitlines()
        lowered_terms = [t.lower() for t in terms]
        hit_idx: list[int] = []
        for i, ln in enumerate(lines):
            low = ln.lower()
            if any(t in low for t in lowered_terms):
                hit_idx.append(i)
        if not hit_idx:
            return ""
        chosen: list[int] = []
        for i in hit_idx:
            for j in (i - 1, i, i + 1):
                if 0 <= j < len(lines):
                    chosen.append(j)
        # 保序去重
        uniq: list[int] = []
        seen: set[int] = set()
        for j in chosen:
            if j in seen:
                continue
            seen.add(j)
            uniq.append(j)
        uniq = uniq[: max(1, max_lines)]
        snippet = "\n".join(lines[j] for j in uniq).strip()
        return snippet

    def search_lore_by_query(
        self,
        query: str,
        tags: Optional[list[str]] = None,
        max_hits: int = 5,
        max_chars_per_hit: int = 600,
    ) -> str:
        """
        在 lores 中做“类 grep”检索，返回可直接拼入 prompt 的文本块。
        """
        terms = self._extract_query_terms(query)
        if not terms:
            return ""
        if not self.data_path.exists():
            return ""

        want = {str(t).strip() for t in (tags or []) if str(t).strip()}
        rows: list[tuple[int, str, str]] = []
        for file_path in self._scan_markdown_files():
            tag = self._path_to_tag(file_path)
            if want and tag not in want:
                continue
            try:
                md = file_path.read_text(encoding="utf-8")
            except Exception:
                continue
            lower_md = md.lower()
            score = sum(lower_md.count(t.lower()) for t in terms)
            if score <= 0:
                continue
            snippet = self._best_snippet(md, terms)
            if not snippet:
                continue
            if max_chars_per_hit > 0 and len(snippet) > max_chars_per_hit:
                snippet = snippet[:max_chars_per_hit]
            rows.append((score, tag, snippet))

        if not rows:
            return ""
        rows.sort(key=lambda x: (-x[0], x[1]))
        parts: list[str] = []
        for score, tag, snippet in rows[: max(1, max_hits)]:
            parts.append(f"【{tag}｜match={score}】\n{snippet}")
        return "### 背景设定检索（grep） ###\n\n" + "\n\n".join(parts)