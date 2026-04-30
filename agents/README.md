# `agents/` — 各文件职责

本目录为小说 Agent 的 Python 领域代码（编排 LLM、状态、提示词、持久化、设定加载）。

**分层依赖、请求链路、数据真源、修改联动**见仓库根目录 [`../ARCHITECTURE.md`](../ARCHITECTURE.md)。  
**磁盘字段与表关联**见 [`../storage/README.md`](../storage/README.md)。

---

## 根目录文件

| 文件 | 作用 |
|------|------|
| `README.md` | 本文件 |
| `_internal_marks.py` | 模块指纹登记（配合 [`../SECURITY_FINGERPRINT.md`](../SECURITY_FINGERPRINT.md)） |
| `text_utils.py` | LLM 响应解析、归档文本落盘等横切工具 |

---

## `novel/`

| 文件 | 作用 |
|------|------|
| `__init__.py` | 导出 `NovelAgent`、`RunResult` 等 |
| `novel_agent.py` | 章节运行主编排：`plan`/`write`/`init`、`run`、`preview_input`，协调 lore/state/prompt/持久化 |
| `llm_client.py` | DeepSeek / LangChain 模型初始化与调用参数 |
| `llm_json.py` | 从模型输出抽取 JSON、解析失败时的修复重试 |
| `structured_invoke.py` | 调模型并解析为 Pydantic 模型（含 JSON 修复与调试落盘） |
| `timeline_focus.py` | 解析当前章聚焦的时间线事件 id（`ev:timeline:*`） |

---

## `state/`

| 文件 | 作用 |
|------|------|
| `__init__.py` | **仅**再导出 `state_models` 类型（避免循环导入） |
| `state_models.py` | `NovelState`、`ChapterPlan`、`ChapterRecord` 等 Pydantic 模型 |
| `state_compactor.py` | 注入模型前的 state 压缩（含 timeline / 图谱邻居等策略） |
| `state_merge.py` | 运行结果与状态的合并（不写盘） |
| `consistency_audit.py` | 章节一致性审计（评分、问题列表、阻断原因、修复动作建议） |
| `chapter_structure.py` | 章节结构卡生成与门禁（自动补齐并锁定、最小项校验、风险确认） |
| `shadow_director.py` | 影子编导策略包（推荐配角/冲突类型/伏笔回收，默认自动接管细节） |

---

## `prompt/`

| 文件 | 作用 |
|------|------|
| `__init__.py` | 包导出 |
| `prompt_builders.py` | 各阶段系统/用户提示词字符串拼装 |

---

## `persistence/`

| 文件 | 作用 |
|------|------|
| `__init__.py` | 包导出 |
| `storage.py` | `novel.db` 中 `novel_state`、章节行的读写与列表 |
| `graph_tables.py` | 四表（人物/事件实体与关系）、hydrate、章节落盘后图谱同步、`persist_chapter_artifacts` 等 |

---

## `lore/`

| 文件 | 作用 |
|------|------|
| `__init__.py` | 包导出 |
| `loader.py` | `LoreLoader`：扫描 `lores/**/*.md`、按 tag 取正文与预览；支持按 query 在 lore 内命中检索并拼接关键片段 |
| `lore_summary.py` | 摘要缓存文件的读写与哈希匹配 |
| `lore_runtime.py` | `build_lorebook`、`build_lore_summary_llm` 等与运行期设定拼装 |

---

## 测试命令

```bash
python -m pytest tests/ -q
```

（时间段等契约测试依赖 `webapp.backend` 对 `run_helpers` 的导出，见 `tests/test_time_slot_infer.py`。）
