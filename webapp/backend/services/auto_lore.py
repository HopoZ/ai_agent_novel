from __future__ import annotations

import json
import os
import shutil
import tempfile
from typing import Any, Dict, List
from uuid import uuid4

from agents.lore.lore_runtime import regenerate_auto_lore_with_graph
from agents.persistence.storage import load_state
from webapp.backend.deps import agent
from webapp.backend.graph_payload import build_novel_graph_payload
from webapp.backend.paths import STORAGE_NOVELS_DIR

AUTO_LORE_FILE_SPECS = [
    "00_项目说明.md",
    "01_世界观骨架.md",
    "02_角色与关系草案.md",
    "03_连载主线与伏笔.md",
]


def auto_lore_manifest_path(novel_id: str):
    return STORAGE_NOVELS_DIR / novel_id / "auto_lore_manifest.json"


def safe_stem_text(v: str) -> str:
    s = "".join(ch for ch in str(v or "").strip() if ch.isalnum() or ch in ("_", "-", " ", "·", "."))
    return s.strip()[:48] or "untitled"


def normalize_auto_lore_filename(name: str) -> str:
    fn = safe_stem_text(name).replace(" ", "_").strip()
    if not fn:
        fn = "untitled"
    fn = fn.rstrip(".")
    if not fn.lower().endswith(".md"):
        fn = f"{fn}.md"
    while fn.lower().endswith(".md.md"):
        fn = fn[:-3]
    return fn


def build_auto_lore_docs(
    *,
    novel_id: str,
    novel_title: str,
    start_time_slot: str,
    pov_character_id: str,
    selected_tags: List[str],
    brief: str,
) -> List[Dict[str, str]]:
    root = f"自动生成/{novel_id}"
    tag_hint = "、".join(selected_tags[:8]) if selected_tags else "（当前未勾选其他设定）"
    title_line = novel_title or "未命名小说"
    slot_line = start_time_slot or "未指定时间段"
    pov_line = pov_character_id or "未指定视角角色"
    brief_line = brief or "无额外说明。"
    files = [
        {
            "filename": "00_项目说明.md",
            "body": (
                f"# 自动设定包（{title_line}）\n\n"
                f"- 小说ID：`{novel_id}`\n"
                f"- 起始时间段：{slot_line}\n"
                f"- 起始视角：{pov_line}\n"
                f"- 创建时已勾选标签：{tag_hint}\n\n"
                "## 说明\n"
                "本目录内容由系统在创建小说时自动生成，可直接编辑。建议保留文件名，便于后续追踪。\n"
            ),
        },
        {
            "filename": "01_世界观骨架.md",
            "body": (
                f"# 世界观骨架 · {title_line}\n\n"
                "## 时代与环境\n"
                f"- 当前起点：{slot_line}\n"
                "- 时代技术层级：\n"
                "- 社会秩序与禁忌：\n"
                "- 资源与冲突稀缺点：\n\n"
                "## 本书核心矛盾\n"
                "- 主矛盾：\n"
                "- 次矛盾：\n"
                "- 触发事件：\n\n"
                "## 作者补充意图\n"
                f"{brief_line}\n"
            ),
        },
        {
            "filename": "02_角色与关系草案.md",
            "body": (
                f"# 角色与关系草案 · {title_line}\n\n"
                "## 主视角\n"
                f"- 角色ID：{pov_line}\n"
                "- 当前目标：\n"
                "- 隐性动机：\n"
                "- 风险与弱点：\n\n"
                "## 关键他者\n"
                "- 角色A：与主视角关系 / 利益冲突 / 可触发事件\n"
                "- 角色B：与主视角关系 / 利益冲突 / 可触发事件\n\n"
                "## 关系变化触发清单\n"
                "- 关系突变前置事件：\n"
                "- 关系逆转关键台词或行动：\n"
            ),
        },
        {
            "filename": "03_连载主线与伏笔.md",
            "body": (
                f"# 连载主线与伏笔 · {title_line}\n\n"
                "## 三段式主线\n"
                "- 第一阶段（铺设）：\n"
                "- 第二阶段（对抗）：\n"
                "- 第三阶段（回收）：\n\n"
                "## 伏笔池（建议至少3条）\n"
                "1. 伏笔内容：\n"
                "   - 埋设章节：\n"
                "   - 回收目标章节：\n"
                "2. 伏笔内容：\n"
                "   - 埋设章节：\n"
                "   - 回收目标章节：\n"
                "3. 伏笔内容：\n"
                "   - 埋设章节：\n"
                "   - 回收目标章节：\n"
            ),
        },
    ]
    docs: List[Dict[str, str]] = []
    for i, it in enumerate(files):
        expected = AUTO_LORE_FILE_SPECS[i] if i < len(AUTO_LORE_FILE_SPECS) else str(it["filename"])
        fn = normalize_auto_lore_filename(expected)
        rel = f"{root}/{fn}"
        docs.append({"relative_path": rel, "tag": rel[:-3], "content": it["body"]})
    return docs


def write_auto_lore_docs(
    *,
    novel_id: str,
    docs: List[Dict[str, str]],
    overwrite: bool,
) -> Dict[str, Any]:
    base = agent.lore_loader.data_path
    generated: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []
    for d in docs:
        rel = str(d.get("relative_path") or "").replace("\\", "/").strip()
        if not rel:
            continue
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        exists = path.exists()
        if exists and (not overwrite):
            skipped.append({"relative_path": rel, "tag": str(d.get("tag") or "")})
            continue
        path.write_text(str(d.get("content") or "").strip() + "\n", encoding="utf-8")
        generated.append({"relative_path": rel, "tag": str(d.get("tag") or "")})

    payload = {
        "novel_id": novel_id,
        "generated": generated,
        "skipped": skipped,
        "count": len(generated),
        "updated_at": str(uuid4()),
    }
    mf = auto_lore_manifest_path(novel_id)
    mf.parent.mkdir(parents=True, exist_ok=True)
    mf.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def collect_existing_auto_lore_docs(novel_id: str) -> List[Dict[str, str]]:
    base = agent.lore_loader.data_path / "自动生成" / novel_id
    rows: List[Dict[str, str]] = []
    if not base.exists():
        return rows
    for fp in base.rglob("*.md"):
        if not fp.is_file():
            continue
        rel = fp.relative_to(agent.lore_loader.data_path).as_posix()
        rows.append({"relative_path": rel, "filename": fp.name, "content": fp.read_text(encoding="utf-8")})
    rows.sort(key=lambda x: str(x.get("relative_path", "")))
    return rows


def build_auto_lore_docs_via_graph_rewrite(
    *,
    novel_id: str,
    novel_title: str,
    brief: str,
    rewrite_fn=None,
) -> List[Dict[str, str]]:
    st = load_state(novel_id)
    if not st:
        raise ValueError("novel not found")
    graph = build_novel_graph_payload(novel_id, st, "mixed")
    old_docs = collect_existing_auto_lore_docs(novel_id)
    model = agent._get_model()
    fn = rewrite_fn or regenerate_auto_lore_with_graph
    rewritten = fn(
        model=model,
        novel_id=novel_id,
        novel_title=novel_title,
        brief=brief,
        old_docs=old_docs,
        state_payload=st.model_dump(mode="json"),
        graph_payload=graph,
        target_filenames=list(AUTO_LORE_FILE_SPECS),
    )
    root = f"自动生成/{novel_id}"
    docs: List[Dict[str, str]] = []
    for row in rewritten:
        fn = normalize_auto_lore_filename(str(row.get("filename") or "").strip())
        content = str(row.get("content") or "").strip()
        if (not fn) or (not content):
            continue
        rel = f"{root}/{fn}"
        docs.append({"relative_path": rel, "tag": rel[:-3], "content": content})
    if len(docs) != len(AUTO_LORE_FILE_SPECS):
        raise ValueError("auto lore rewrite returned incomplete docs")
    return docs


def write_auto_lore_docs_atomic(
    *,
    novel_id: str,
    docs: List[Dict[str, str]],
) -> Dict[str, Any]:
    base = agent.lore_loader.data_path
    tmp_rows: List[tuple[str, Any, str, str]] = []
    generated: List[Dict[str, str]] = []
    try:
        for d in docs:
            rel = str(d.get("relative_path") or "").replace("\\", "/").strip()
            if not rel:
                raise ValueError("invalid relative_path in docs")
            path = base / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            content = str(d.get("content") or "").strip()
            if not content:
                raise ValueError(f"empty content for {rel}")
            tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), suffix=".tmp")
            tmp.write(content + "\n")
            tmp.flush()
            tmp.close()
            tmp_rows.append((str(tmp.name), path, rel, str(d.get("tag") or "")))

        for tmp_name, path, rel, tag in tmp_rows:
            shutil.move(str(tmp_name), str(path))
            generated.append({"relative_path": rel, "tag": tag})
    except Exception:
        for tmp_name, _, _, _ in tmp_rows:
            try:
                os.remove(tmp_name)
            except Exception:
                pass
        raise

    payload = {
        "novel_id": novel_id,
        "generated": generated,
        "skipped": [],
        "count": len(generated),
        "updated_at": str(uuid4()),
    }
    mf = auto_lore_manifest_path(novel_id)
    mf.parent.mkdir(parents=True, exist_ok=True)
    mf.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def validate_regen_docs_constraints(novel_id: str, docs: List[Dict[str, str]]) -> None:
    root = f"自动生成/{novel_id}/"
    allowed = set(AUTO_LORE_FILE_SPECS)
    if len(docs) != len(AUTO_LORE_FILE_SPECS):
        raise ValueError("regen docs must contain exactly 4 files")
    seen: set[str] = set()
    for d in docs:
        rel = str(d.get("relative_path") or "").replace("\\", "/").strip()
        if not rel.startswith(root):
            raise ValueError(f"invalid regen path: {rel}")
        fn = rel[len(root) :]
        if (not fn) or ("/" in fn) or ("\\" in fn):
            raise ValueError(f"invalid regen filename: {fn}")
        if fn not in allowed:
            raise ValueError(f"unexpected regen filename: {fn}")
        if fn in seen:
            raise ValueError(f"duplicate regen filename: {fn}")
        seen.add(fn)
        content = str(d.get("content") or "").strip()
        if not content:
            raise ValueError(f"empty regen content: {fn}")


def read_auto_lore_manifest(novel_id: str) -> Dict[str, Any]:
    mf = auto_lore_manifest_path(novel_id)
    if not mf.exists():
        return {"novel_id": novel_id, "generated": [], "skipped": [], "count": 0}
    try:
        data = json.loads(mf.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"novel_id": novel_id, "generated": [], "skipped": [], "count": 0}


def generate_auto_lore_for_novel(
    *,
    novel_id: str,
    novel_title: str,
    start_time_slot: str,
    pov_character_id: str,
    lore_tags: List[str],
    brief: str,
    overwrite: bool,
) -> Dict[str, Any]:
    docs = build_auto_lore_docs(
        novel_id=novel_id,
        novel_title=novel_title,
        start_time_slot=start_time_slot,
        pov_character_id=pov_character_id,
        selected_tags=lore_tags,
        brief=brief,
    )
    return write_auto_lore_docs(novel_id=novel_id, docs=docs, overwrite=overwrite)

