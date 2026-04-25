from __future__ import annotations

from pathlib import Path
from typing import List

import pytest
from fastapi import HTTPException

from agents.persistence.storage import load_state, save_state
from webapp.backend.routes import novels
from webapp.backend.schemas import AutoLoreRegenerateRequest, CreateNovelRequest


def _set_test_paths(monkeypatch, tmp_path: Path) -> Path:
    storage = tmp_path / "storage"
    outputs = tmp_path / "outputs"
    lores = tmp_path / "lores"
    monkeypatch.setenv("NOVEL_AGENT_STORAGE_DIR", str(storage))
    monkeypatch.setenv("NOVEL_AGENT_OUTPUTS_DIR", str(outputs))
    monkeypatch.setenv("NOVEL_AGENT_LORES_DIR", str(lores))
    monkeypatch.setenv("SKIP_FRONTEND_BUILD", "1")
    lores.mkdir(parents=True, exist_ok=True)
    novels.agent.lore_loader.data_path = lores
    monkeypatch.setattr(novels.agent, "_get_model", lambda: object())
    return lores


def _seed_auto_lore_files(lores_dir: Path, novel_id: str, prefix: str) -> None:
    root = lores_dir / "自动生成" / novel_id
    root.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(novels.AUTO_LORE_FILE_SPECS):
        (root / name).write_text(f"{prefix}-{i}\n", encoding="utf-8")


def test_regenerate_auto_lore_success_overwrite(monkeypatch, tmp_path):
    lores = _set_test_paths(monkeypatch, tmp_path)
    created = novels.create_novel(
        CreateNovelRequest(
            novel_title="重生成成功样本",
            start_time_slot="起点",
            pov_character_id="hero",
            lore_tags=["custom/base"],
            auto_generate_lore=False,
        )
    )
    novel_id = str(created["novel_id"])
    _seed_auto_lore_files(lores, novel_id, "old")

    def _fake_rewrite(**kwargs):
        return [{"filename": name, "content": f"new-content-{i}"} for i, name in enumerate(novels.AUTO_LORE_FILE_SPECS)]

    monkeypatch.setattr(novels, "regenerate_auto_lore_with_graph", _fake_rewrite)

    payload = novels.regenerate_auto_lore(novel_id, AutoLoreRegenerateRequest(brief="按图谱重写", overwrite=True))
    assert int(payload["count"]) == 4

    root = lores / "自动生成" / novel_id
    for i, name in enumerate(novels.AUTO_LORE_FILE_SPECS):
        text = (root / name).read_text(encoding="utf-8")
        assert f"new-content-{i}" in text


def test_regenerate_auto_lore_fail_fast_no_write(monkeypatch, tmp_path):
    lores = _set_test_paths(monkeypatch, tmp_path)
    created = novels.create_novel(
        CreateNovelRequest(
            novel_title="重生成失败样本",
            auto_generate_lore=False,
        )
    )
    novel_id = str(created["novel_id"])
    _seed_auto_lore_files(lores, novel_id, "stable-old")

    def _raise_rewrite(**kwargs):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(novels, "regenerate_auto_lore_with_graph", _raise_rewrite)

    with pytest.raises(HTTPException) as err:
        novels.regenerate_auto_lore(novel_id, AutoLoreRegenerateRequest(brief="触发失败", overwrite=True))
    assert err.value.status_code == 400
    assert "未覆盖任何文件" in str(err.value.detail)

    root = lores / "自动生成" / novel_id
    for i, name in enumerate(novels.AUTO_LORE_FILE_SPECS):
        text = (root / name).read_text(encoding="utf-8")
        assert f"stable-old-{i}" in text


def test_regenerate_auto_lore_keeps_only_own_auto_tags(monkeypatch, tmp_path):
    lores = _set_test_paths(monkeypatch, tmp_path)
    created_a = novels.create_novel(CreateNovelRequest(novel_title="A书", auto_generate_lore=False))
    created_b = novels.create_novel(CreateNovelRequest(novel_title="B书", auto_generate_lore=False))
    novel_a = str(created_a["novel_id"])
    novel_b = str(created_b["novel_id"])
    _seed_auto_lore_files(lores, novel_a, "a-old")
    _seed_auto_lore_files(lores, novel_b, "b-old")

    st = load_state(novel_a)
    assert st is not None
    st.meta.lore_tags = [
        "custom/tag",
        f"自动生成/{novel_b}/00_项目说明",
    ]
    save_state(novel_a, st)

    def _fake_rewrite(**kwargs):
        return [{"filename": name, "content": f"a-new-{i}"} for i, name in enumerate(novels.AUTO_LORE_FILE_SPECS)]

    monkeypatch.setattr(novels, "regenerate_auto_lore_with_graph", _fake_rewrite)
    payload = novels.regenerate_auto_lore(novel_a, AutoLoreRegenerateRequest(brief="一致性检查", overwrite=True))
    generated: List[str] = [str(x.get("tag") or "") for x in payload.get("generated", [])]
    assert generated
    assert all(tag.startswith(f"自动生成/{novel_a}/") for tag in generated)

    st_after = load_state(novel_a)
    assert st_after is not None
    tags = [str(x) for x in (st_after.meta.lore_tags or [])]
    assert "custom/tag" in tags
    assert any(tag.startswith(f"自动生成/{novel_a}/") for tag in tags)
    assert not any(tag.startswith(f"自动生成/{novel_b}/") for tag in tags)


def test_regenerate_auto_lore_normalizes_missing_md_suffix(monkeypatch, tmp_path):
    lores = _set_test_paths(monkeypatch, tmp_path)
    created = novels.create_novel(CreateNovelRequest(novel_title="后缀规范样本", auto_generate_lore=False))
    novel_id = str(created["novel_id"])
    _seed_auto_lore_files(lores, novel_id, "seed")

    def _fake_rewrite(**kwargs):
        return [
            {"filename": "00_项目说明", "content": "a"},
            {"filename": "01_世界观骨架.md", "content": "b"},
            {"filename": "02_角色与关系草案.md.md", "content": "c"},
            {"filename": "03_连载主线与伏笔", "content": "d"},
        ]

    monkeypatch.setattr(novels, "regenerate_auto_lore_with_graph", _fake_rewrite)
    payload = novels.regenerate_auto_lore(novel_id, AutoLoreRegenerateRequest(brief="后缀归一", overwrite=True))
    assert int(payload["count"]) == 4
    root = lores / "自动生成" / novel_id
    for name in novels.AUTO_LORE_FILE_SPECS:
        assert (root / name).exists()
