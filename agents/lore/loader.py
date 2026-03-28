# 负责加载设定文件并构建创作百科全书的上下文信息

from pathlib import Path
from typing import Dict, List

class LoreLoader:
    def __init__(self, data_path="settings"):
        # Web 启动时工作目录可能变化；把相对路径固定到仓库根目录
        # agents/lore/loader.py -> 仓库根为向上两级
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
        递归扫描 settings/**/*.md（忽略 README.md），返回相对路径排序列表。
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
        settings/world/faction.md -> world/faction
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
        返回 settings/**/*.md 的标签（保留目录层级）。
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