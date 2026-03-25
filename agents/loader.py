# 负责加载设定文件并构建创作百科全书的上下文信息

import os
from pathlib import Path

class LoreLoader:
    def __init__(self, data_path="settings"):
        # Web 启动时工作目录可能变化；把相对路径固定到仓库根目录
        repo_root = Path(__file__).resolve().parents[1]
        p = Path(data_path)
        self.data_path = p if p.is_absolute() else (repo_root / p)

    def get_lore_tags(self):
        """返回 settings/*.md 的标签（文件名去掉扩展名），用于 Web 页面展示/调试。"""
        if not self.data_path.exists():
            return []
        tags = []
        for file in sorted(os.listdir(self.data_path)):
            if file.endswith(".md"):
                tags.append(file.replace(".md", ""))
        return tags

    def get_lore_by_tags(self, tags: list[str]) -> str:
        """
        读取指定 tags 对应的 markdown，并拼成 lorebook 文本块。
        """
        if not self.data_path.exists():
            return ""
        want = set(tags)
        full_context = "### 创作百科全书 (Lorebook) ###\n"
        # 为稳定性仍按文件名排序输出
        for file in sorted(os.listdir(self.data_path)):
            if not file.endswith(".md"):
                continue
            tag = file.replace(".md", "")
            if tag not in want:
                continue
            file_path = self.data_path / file
            with open(file_path, "r", encoding="utf-8") as f:
                full_context += f"\n【{tag}】:\n{f.read()}\n"
        return full_context

    def get_markdown_by_tag(self, tag: str) -> str:
        """
        读取单个 settings/<tag>.md 的原始 markdown 内容。
        """
        if not self.data_path.exists():
            return ""
        file_path = self.data_path / f"{tag}.md"
        if not file_path.exists():
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