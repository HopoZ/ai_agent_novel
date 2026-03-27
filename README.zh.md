## AI Novel Agent

设定驱动的长篇小说生成系统。  
围绕 `settings/*.md`（SSOT）构建 `plan -> write -> state update -> persist` 闭环，提供 Web 流式写作、输入可观测与图谱可视化。

## 核心能力

- **状态持续写作**：`NovelState` 持久化人物、世界、时间线、连续性
- **流式生成（SSE）**：`planning/auto_init/writing/saving/done`
- **结构化容错**：JSON repair + `next_state` patch merge
- **Lore 摘要链路**：
  - LLM 摘要（非规则抽取）
  - 单 tag 缓存（`llm_tag_v1`）
  - 缓存未命中自动回退原文
- **输入可观测**：`/preview_input` 查看真实拼装输入
- **图谱视图**：`people / events / mixed`
- **Token 可见性**：前端展示 auto_init 与正文阶段 token

## 运行模式

| 模式 | 说明 |
|---|---|
| `init_state` | 初始化世界状态 |
| `plan_only` | 仅生成章节规划并更新状态 |
| `write_chapter` | 规划 + 正文生成 + 落盘 |
| `revise_chapter` | 修订（当前沿用规划+写作链路） |

## Lore 与上下文策略

### Lore 注入
- 运行链路基于 `lore_tags`（不依赖 `lore_summary_id`）
- 每个 tag 优先读取摘要缓存，未命中回退原文
- “生成当前Tag摘要”按当前勾选 tags 主动生成
- 摘要接口返回 `tag_summaries: [{ tag, summary }]`

### 章节上下文
- 默认仅注入相邻相关两章
- 手动设置 `time_slot_override` 时不注入章节 JSON 上下文
- 章节 JSON 的 `content` 不进入核心上下文，控制 token 消耗

### 悬浮预览
- `compact=1` 显示 tag 摘要预览
- 若无该 tag 缓存，提示先生成摘要

## 架构

```text
[Presentation]
Vue3 + Element Plus + ECharts
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

## 快速开始

### 1) 安装依赖
```bash
pip install -r requirements.txt
```

### 2) 配置密钥
项目根目录创建 `.env`：
```bash
DEEPSEEK_API_KEY=<your_api_key>
```

### 3) 准备设定
将 Markdown 设定文件放入 `settings/`。

### 4) 启动服务
```bash
python -m uvicorn webapp.server:app --reload --port 8000
```
访问：`http://127.0.0.1:8000/`

## 常见问题

### WinError 2（启动时找不到 npm）
原因：uvicorn 进程 PATH 与交互终端 PATH 不一致。  
当前行为：Windows 自动构建优先 `npm.cmd`；找不到时记录 warning 并跳过自动构建。

## 许可证

- AGPL-3.0-or-later（`LICENSE`）
- 作者信息见 `NOTICE`

