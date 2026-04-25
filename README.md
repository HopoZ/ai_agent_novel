# AI Novel Agent

面向长篇网文 / 系列叙事的工程化写作系统：以 `lores/` 下 Markdown 为设定来源，用 **plan → write → state 更新 → 持久化** 形成可迭代的创作闭环；提供 **FastAPI + Vue 3** 的 Web 工作台（Input 预览、SSE 流式输出、知识图谱编辑），以及可选的终端 CLI 与 Flet 移动端示例。

**预览**

| Web 工作台 | 知识图谱 |
|-----------|---------|
| ![Web](./images/网页端.jpg) | ![Graph](./images/图谱.jpg) |

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3、TypeScript、Vite、Element Plus、ECharts；可选 Electron 桌面壳 |
| 后端 | Python 3、FastAPI、LangChain（DeepSeek + OpenAI 兼容 API） |
| 领域 | `NovelAgent`、状态压缩与合并、图谱四表持久化、Lore 摘要缓存 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API 密钥

统一在 Web 端右上角「API 密钥」里配置并保存（本地 `storage/user_settings.json`）：

- `DeepSeek`：填写 API Key
- `OpenAI 兼容`：填写 API Key + Base URL + Model

当前项目默认按前端/Electron 本地配置生效，不再依赖环境变量优先级。

### 3. 准备设定

将 Markdown 设定放入 `lores/`（相对路径即标签空间，供勾选与注入）。


### 开始（三选一）
####  启动 Web

在**仓库根目录**执行：

```bash
python -m uvicorn webapp.backend.server:app --reload --port 8000
```

浏览器访问：`http://127.0.0.1:8000/`

- 启动时会尝试构建前端（`webapp/frontend` → `dist/`）。若已自行构建或想跳过：设置环境变量 `SKIP_FRONTEND_BUILD=1`。
- 单独开发前端：`cd webapp/frontend && npm install && npm run dev`（代理与端口以 `vite.config.ts` 为准）。

####  终端 CLI

不经过 Web 状态机，仅多轮对话 + Lore 原文注入：

```bash
python -m cli
```

默认使用 DeepSeek **深度思考**模型（`deepseek-reasoner`），终端流式区分「深度思考」与「正文」，会话文件与多轮历史仅保留正文以便 API 兼容。加 `--fast` 可改用 `deepseek-chat`。

####  Electron 桌面壳

[下载地址](https://github.com/HopoZ/ai_agent_novel/releases)

---

## 功能要点

- **先预览再运行**：主流程先请求 `preview_input`，确认后再 `run_stream`，减少误触耗 token。
- **流式与可中止**：规划 / 正文 / 优化建议等 SSE 阶段可观察；可中止以节省 token。
- **影子编导（轻介入）**：预输入阶段给出推荐挂载事件；可一键采用，未显式选事件时可自动托底采用，减少时序手工成本。
- **结构卡门禁（写前约束）**：预览阶段自动补齐并锁定结构卡（目标/冲突/转折/伏笔回收/事件归属）；最小项不满足时需“继续生成（风险）”确认。
- **一致性审计 v2（可阻断）**：写作完成后返回评分、问题、阻断原因与修复动作；内置时间线反转、角色瞬移、关系突变无依据等高危规则，高危冲突可阻断“下章续写”自动链。
- **下章续写（内联）**：写章、修订、扩写或优化完成后，在右侧「下章建议」栏内直接编辑并一键生成下一章（沿用「生成正文」同款预览链），并尽量自动绑定本章时间线事件。
- **影子编导 v2（自动细节接管）**：推荐配角、冲突类型、伏笔回收策略；默认自动采用，支持一键撤销最近一次自动导演。
- **新建自动设定包**：创建小说时可自动生成 `lores/自动生成/<novel_id>/` 设定草案（世界观骨架、角色关系、主线伏笔），并支持在界面“自动设定”入口重生成与查看。
- **Tag 内置管理（含批量）**：左栏可直接新建/重命名/删除/编辑 Tag，支持批量删除与批量前缀迁移，且会同步更新小说已绑定 `lore_tags`。
- **图谱专业管理**：人物 / 事件 / 混合视图，全屏编辑节点与边；支持节点/边类型筛选、孤立节点检查、命中计数搜索、新建后自动聚焦、导出 JSON 快照（数据落在 `storage/novels/<id>/novel.db` 四表与 `novel_state`）。
- **图谱交互增强（最新）**：支持右键拖线连边（人物关系 / 时间推进 / 出场 / 章节归属）；剧情事件网按 `timeline_next` 自动横向排序，并支持“按选中事件展开章节 / 展开或收起全部章节”。
- **图谱高级操作抽屉**：批量删边从主面板收纳到二级“高级操作”入口，减少主界面占用。
- **模型提供商体验增强（V1）**：OpenAI 兼容模型列表支持后端 TTL 缓存 + 前端会话缓存、强制刷新入口，并展示模型能力标签（chat / vision / tool / reasoning）辅助选型。
- **前端导演工作台**：中栏改为单屏工作台（Step1~4 手动流转，阶段完成后高亮下一步，非当前步骤默认隐藏，支持“下一步/上一步”），运行结果改为抽屉面板；图谱采用紧凑切片 + 全屏工作室双形态；Step3 任务为空时自动推测草案，作者可改写确认。

---

## 运行模式（`RunModeRequest.mode`）

| 模式 | 说明 |
|------|------|
| `init_state` | 初始化世界（写作前需已初始化） |
| `plan_only` | 仅章节规划并更新状态 |
| `write_chapter` | 规划 + 正文 + 落盘 |
| `revise_chapter` | 修订（沿用规划 + 写作链路） |
| `expand_chapter` | 扩写（写作阶段为 expand） |
| `optimize_suggestions` | 优化建议（独立链路，非整章落盘主链） |

---

## 仓库结构（简）

```text
agents/              # 领域：NovelAgent、状态、提示词、持久化、Lore
webapp/backend/      # FastAPI：路由、SSE、schemas、run_helpers、graph_payload
webapp/frontend/     # Vue 3 工作台源码
lores/               # 设定 Markdown（可按 .gitignore 决定是否入库）
storage/             # 运行数据、摘要缓存、按小说分目录
outputs/             # 正文归档（按小说分子目录）
cli.py               # 终端入口
electron/            # Electron 壳（子进程 uvicorn + 窗口）
mobile/              # Flet 客户端示例
```

---

## 数据与接口（摘要）

持久化要点：

- **单本小说数据**：`storage/novels/<id>/novel.db`（SQLite：`novel_state`、章节行、图谱四表）
- **运行态叙事状态**：`novel_state` 表中的 `NovelState` JSON（人物关系边以四表为准）
- **图谱**：人物/事件实体与关系存于上述 DB，与 API `GET/PATCH/POST/DELETE /api/novels/{id}/graph*` 对应

常用 HTTP 示例：

- `POST /api/lore/summary/build`、`GET /api/lore/tags`、`GET /api/lore/preview`
- `POST /api/novels/{id}/preview_input`、`POST /api/novels/{id}/run_stream`（SSE）
- `POST /api/novels/{id}/run`（非流式 JSON）

完整字段与行为以代码为准：`webapp/backend/schemas.py`、`agents/`、`storage/` 下说明（若仓库中包含对应文档）。

---

## 设计取向（简）

- **连续性**：状态机驱动，而非单次生成即弃。
- **设定可控**：标签化 Lore，摘要缓存 + 未命中回退原文。
- **可观测**：阶段事件、token 提示、Input 可预览。
- **稳健**：结构化输出与合并策略，降低长输出失败成本。

实践建议：先为常用 tag 生成摘要再写章；按章收敛任务；人物与事件关系以图谱表为事实源，再进入生成。

---

## 路线图

功能进度与计划见 [TOURMAP.md](./TOURMAP.md)。

---

## 许可证与作者

- **许可证**：AGPL-3.0-or-later，见 [LICENSE](./LICENSE)。
- **作者**：见 [NOTICE](./NOTICE)。
