# AI Novel Agent

- 中文文档: [README.zh.md](./README.zh.md)
- English docs: [README.en.md](./README.en.md)

## AI Novel Agent

Lore-driven, stateful long-form fiction generation system.

面向长篇网文/系列小说，围绕 `settings/*.md`（SSOT）构建稳定写作闭环：
`plan -> write -> state update -> persist`，并提供 Web 流式体验与图谱可视化。

## What It Solves

- 设定分散、反复漂移：以 `settings/` 作为统一设定源
- 长文连续性难维护：以 `NovelState` 持久化人物/世界/时间线
- 黑盒 prompt 难排查：支持输入预览与阶段化流式日志
- token 失控：上下文裁剪 + lore 摘要缓存

## Core Features

- **Stateful writing loop**: `NovelState` 持久化并逐章演进
- **SSE streaming**: `planning/auto_init/writing/saving/done`
- **Structured + fault-tolerant**: JSON repair + `next_state` patch merge
- **Lore summary pipeline**:
  - LLM 摘要（非规则抽取）
  - 单 tag 粒度缓存（`llm_tag_v1`）
  - 未命中缓存自动回退原文，避免信息丢失
- **Prompt observability**: `/preview_input` 查看真实拼装输入
- **Graph view**: `people / events / mixed`
- **Token usage display**: 前端显示 auto_init 与正文阶段 token

## Run Modes

| Mode | Description |
|---|---|
| `init_state` | 初始化世界状态 |
| `plan_only` | 只生成章节规划并更新状态 |
| `write_chapter` | 规划 + 正文生成 + 落盘 |
| `revise_chapter` | 修订（当前沿用规划+写作链路） |

## Lore & Context Strategy

### Lore injection

- 运行链路基于 `lore_tags`（不依赖 `lore_summary_id`）
- 每个 tag 优先读取摘要缓存；未命中回退该 tag 原文
- “生成当前Tag摘要”按当前勾选 tags 主动生成
- 摘要返回结构化 `tag_summaries: [{ tag, summary }]`

### Chapter context

- 默认仅注入相邻相关两章
- 手动设置 `time_slot_override` 时不注入章节 JSON 上下文
- 章节 JSON 的 `content` 不进入核心上下文，降低 token 压力

### Hover preview

- `compact=1` 显示 tag 摘要预览
- 若该 tag 尚无摘要缓存，提示先生成摘要

## Architecture

```text
[Presentation]
Vue3 + Element Plus + ECharts
  - Tag selector / Role control
  - SSE streaming UI
  - Graph visualization
        |
        v
[API]
FastAPI (webapp/server.py)
  - /api/novels/*
  - /api/lore/*
  - /api/novels/*/graph
  - /api/novels/*/run_stream
        |
        v
[Domain]
NovelAgent (agents/novel_agent.py)
  - build_lore_summary_llm
  - plan_chapter / write_chapter_text
  - merge_state
  - preview_input
        |
        v
[Data]
settings/*.md
storage/lore_summaries/*.json
storage/novels/<id>/{state.json, chapters/*.json}
outputs/*.txt
```

## Quick Start

### 1) Install

```bash
pip install -r requirements.txt
```

### 2) Configure key

Create `.env` in project root:

```bash
DEEPSEEK_API_KEY=<your_api_key>
```

### 3) Prepare lore files

Put markdown lore files under `settings/`:

```text
settings/
  角色/男主.md
  角色/女主.md
  世界/等级设定.md
  世界/辅助体系.md
```

### 4) Run server

```bash
python -m uvicorn webapp.server:app --reload --port 8000
```

Open: `http://127.0.0.1:8000/`

## Project Layout

```text
agents/
  novel_agent.py
  lore_summary.py
  storage.py

webapp/
  server.py
  frontend/

storage/
  novels/
  lore_summaries/

settings/
outputs/
```

## Common Issue

### WinError 2 (`npm` not found on startup)

Cause: uvicorn process PATH differs from interactive terminal PATH.

Current behavior:
- Windows startup build prefers `npm.cmd`
- If not found, server logs warning and skips auto frontend build

## License

- AGPL-3.0-or-later (`LICENSE`)
- Author info: `NOTICE`

🚀 AI Novel Agent
A Lore-driven, Stateful Long-form Fiction Generation System

    设定驱动 · 状态持续 · 流式写作 · 可观测输入 · 图谱可视化

📌 Overview（项目简介）

AI Novel Agent 是一个面向长篇网文 / 系列小说的 工程化写作系统（Engineering-grade Writing System）。

系统以：

    settings/*.md 作为 单一真实来源（SSOT, Single Source of Truth）

    构建 规划 → 写作 → 状态更新 → 持久化 的闭环

    支持 长上下文稳定写作（Long-horizon consistency）

并提供：

    🌐 Web 流式写作体验（SSE Streaming）

    🧠 状态持久化（Stateful Narrative Engine）

    🕸️ 知识图谱可视化（Narrative Graph）

✨ Highlights（核心亮点）
🧠 1. Lorebook-first 架构（设定驱动）

    所有设定集中在 settings/

    按 tag 精确注入模型上下文

    避免：

    ❌ 设定散落在 prompt
    ❌ 多轮对话导致设定漂移（Lore Drift）

🔄 2. Stateful Writing Loop（状态驱动写作循环）

核心状态模型：

NovelState（持久化）
├─ characters（人物状态）
├─ world（世界设定）
├─ timeline（时间线）
└─ continuity（连续性约束）

👉 持久化位置：

storage/novels/<id>/state.json

⚡ 3. 流式写作体验（SSE Streaming）

后端通过 Server-Sent Events (SSE) 推送：

planning → auto_init → writing → saving → done

前端实时展示：

    正文生成（token streaming）

    阶段状态（phase-aware UI）

🧱 4. 结构化输出 + 容错（Structured + Fault-tolerant）

LLM 输出：

JSON
{
  "content": "...",
  "next_state": { "patch": ... }
}

关键机制：

    ✅ JSON repair（自动修复）

    ✅ patch merge（状态增量更新）

    ✅ 避免长 JSON 截断崩溃

🧾 5. Lore Summary Pipeline（设定摘要系统）
核心策略：

    单 tag 粒度缓存（granular caching）

    LLM 生成摘要（非规则压缩）

    fallback 原文（信息不丢）

storage/lore_summaries/*.json

👁️ 6. 输入可观测（Prompt Observability）

支持：

/preview_input

👉 可以看到：

    实际喂给模型的 prompt

    lore 注入内容

    上下文拼接方式

🕸️ 7. Narrative Graph（知识图谱）

三种视图：

    👤 people（人物关系）

    📜 events（事件流）

    🔀 mixed（混合）

技术栈：

    后端：Graph Aggregation

    前端：ECharts Force Graph

🏗️ Architecture（系统架构）

[ Presentation Layer ]
Vue3 + Element Plus + ECharts
 ├─ Tag Selector / Role Control
 ├─ SSE Streaming UI
 └─ Graph Visualization

            ↓ REST + SSE

[ API Layer ]
FastAPI (webapp/server.py)
 ├─ /api/novels/*
 ├─ /api/lore/*
 ├─ /graph
 └─ /run_stream (SSE)

            ↓

[ Domain Layer ]
NovelAgent
 ├─ plan_chapter
 ├─ write_chapter_text (stream)
 ├─ merge_state (patch)
 ├─ build_lore_summary
 └─ preview_input

            ↓

[ Data Layer ]
File-based Storage
 ├─ settings/*.md
 ├─ state.json
 ├─ chapters/*.json
 └─ lore summaries

🔄 Core Workflow（核心执行链路）

User Input
  ↓
run_stream (SSE)
  ↓
plan_chapter
  ↓
write_chapter (stream)
  ↓
merge_state
  ↓
save chapter + state
  ↓
done

🧠 Lore Injection Strategy（设定注入策略）
优先级（Priority）

    tag summary（命中缓存）

    fallback 原文（未命中）

上下文控制（Context Control）

    默认：只注入相邻两章

    手动时间覆盖：不注入章节 JSON

    content 不进入核心上下文（节省 token）

⚙️ Run Modes（运行模式）
Mode	Description
init_state	初始化世界
plan_only	仅生成章节规划
write_chapter	完整生成
revise_chapter	修订
🚀 Quick Start
1. 安装依赖

Bash
pip install -r requirements.txt

2. 配置 API Key

Bash
# .env
DEEPSEEK_API_KEY=your_key

3. 准备设定

settings/
 ├─ 角色/男主.md
 ├─ 角色/女主.md
 ├─ 世界/等级.md
 └─ 世界/体系.md

4. 启动服务

Bash
python -m uvicorn webapp.server:app --reload --port 8000

访问：

http://127.0.0.1:8000/

📂 Project Structure

agents/
 ├─ novel_agent.py
 ├─ lore_summary.py
 └─ storage.py

webapp/
 ├─ server.py
 └─ frontend/

storage/
 ├─ novels/
 └─ lore_summaries/

settings/
outputs/

⚠️ Common Issues（常见问题）
❗ WinError 2（npm 找不到）

原因：

    PATH 不一致

    uvicorn 子进程找不到 npm

解决：

    使用 npm.cmd（已兼容）

    或手动 build frontend

🧪 Engineering Highlights（工程能力考点）
📌 核心考点（Key Points）

    状态机设计（State Machine）

    LLM 输出结构化（Structured Generation）

    JSON 修复（JSON Repair）

    流式响应（SSE Streaming）

    Prompt 可观测性（Observability）

    上下文压缩（Context Compression）

⚠️ 易混点（Common Pitfalls）
问题	本质
写作不连贯	没有 state
token 爆炸	上下文未裁剪
JSON 崩溃	未做 repair
设定冲突	无 SSOT
前端卡顿	非流式
📜 License

AGPL-3.0-or-later
👤 Author

HopoZ
📧 phmath41@gmail.com
