# `webapp/backend` — 文件说明

FastAPI 后端，负责 HTTP 路由、请求校验、SSE，以及与 `agents` 的编排衔接。

**整体架构、主链路、图谱/Lore 行为、联调清单**见 [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md)。  
前端工程见 [`../frontend/README.md`](../frontend/README.md)。  
静态与模板：`webapp/static/`、`webapp/templates/`；前端构建产物：`webapp/frontend/dist/`。

---

## 运行

在**仓库根目录**：

```bash
python -m uvicorn webapp.backend.server:app --reload --port 8000
```

IPC worker 调试（供 Electron Named Pipe 主链）：

```bash
set NOVEL_AGENT_PIPE_PATH=\\.\pipe\ai_novel_agent_dev_manual
python -m webapp.backend.ipc_pipe_worker
```

| 环境变量 | 作用 |
|----------|------|
| `SKIP_FRONTEND_BUILD=1` | 跳过后端启动时的 `npm run build`，仅用已有 `dist/` |
| `WEBAPP_ENABLE_IPC_WRITE_STREAM=1` | `run_stream` 写正文阶段改为子进程 IPC 流式生成（原型开关） |
| `NOVEL_AGENT_PIPE_PATH` | Electron 全栈 IPC 模式下，Python worker 连接的 Named Pipe 路径 |

---

## 文件与 `routes/`

| 路径 | 作用 |
|------|------|
| `README.md` | 本文件 |
| `__init__.py` | 包标识 |
| `server.py` | ASGI 导入目标：导出 `app`、`create_app`；测试用 `_infer_time_slot` 别名 |
| `app.py` | `create_app()`：CORS、请求日志中间件、`/static`、挂载子路由、启动时可选前端构建 |
| `deps.py` | 单例 `NovelAgent`、命名 logger |
| `paths.py` | 相对仓库根的路径常量（Vite、`storage/novels` 等） |
| `schemas.py` | Pydantic 请求/响应模型（含 `RunModeRequest`：`structure_card` / `structure_risk_ack` / `shadow_director_guidance`，`ApiModelListRequest.force_refresh`，`CreateNovelRequest.auto_generate_lore/auto_lore_brief`，以及图谱 `Graph*`） |
| `frontend_assets.py` | `dist` 新鲜度、`npm build`、挂载 `/assets` |
| `sse.py` | `run_stream` 的 SSE 帧封装 |
| `ipc_chapter_writer.py` | IPC 原型：子进程执行 `write_chapter_text_stream`，主进程通过队列转发增量 |
| `ipc_pipe_worker.py` | Named Pipe worker：接收 Electron 主进程请求并在进程内调用 FastAPI app |
| `run_helpers.py` | 时间段推导、`user_task` 拼接、章节-事件辅助、写前图骨架；含影子编导 guidance 注入；**无** FastAPI 依赖 |
| `domain/README.md` | 领域规则目录说明（本次新增） |
| `domain/novel_lore_tags.py` | 小说 lore tag 作用域与规范化规则（从 routes/novels.py 下沉） |
| `services/README.md` | 服务编排目录说明（本次新增） |
| `services/auto_lore.py` | 自动设定构建/重写/原子写入/manifest 逻辑（从 routes/novels.py 下沉） |
| `services/novel_run.py` | 运行流程共用逻辑（事件绑定校验、错误码推断、plan payload 解包） |
| `graph_payload.py` | 由 `state` + 四表拼装 `GET /graph` 的 nodes/edges JSON（只读） |
| `routes/__init__.py` | 路由包 |
| `routes/README.md` | 路由层职责边界说明 |
| `routes/pages.py` | `GET /`：Vite `index.html` 或旧模板回退 |
| `routes/settings.py` | `/api/settings`、`/api/settings/api_key`、`/api/settings/models`、`/api/settings/test_connection`（LLM 提供商配置、模型列表、连通性测试；模型列表支持后端 TTL 缓存 + `force_refresh` 强刷，并返回 `model_items.capabilities`） |
| `routes/lore.py` | `/api/lore/*`：`POST summary/build`、`GET summary/{id}`、`GET tags`、`GET preview`，以及 Tag 文件管理：`POST/PATCH/DELETE /tags`、`PUT /tags/content`、`POST /tags/batch_delete`、`POST /tags/batch_replace_prefix`（批量操作会同步小说已绑定 lore_tags） |
| `routes/novels.py` | `/api/novels/*`：列表、创建、`state`、`character_entities`、按章 `chapters/{i}`、`anchors`、`run`、`preview_input`、`run_stream`；支持创建时自动生成 lores 草案、`/auto_lore` 查询与 `/auto_lore/regenerate` 重生成；写作模式包含结构卡校验 `structure_gate`、建议策略 `shadow_director`（自动采用 + 可撤销）与写后 `consistency_audit`（时间线反转、角色瞬移、关系突变等阻断规则）；流式 planning 支持 `ChapterPlan/result/output` 包装解包；正文 outputs 按小说分目录落盘 |
| `routes/graph.py` | `/api/novels/{id}/graph`（GET）；`PATCH graph/node`、`POST graph/nodes`、`DELETE graph/nodes`、`POST graph/relationship`、`PATCH timeline-neighbors`、`PATCH graph/edge` |

---

## 桌面 IPC 路径

在 Electron 桌面端（IPC 分支）中，请求链路是：

`renderer(api/client.ts) -> preload -> ipcMain -> Named Pipe -> ipc_pipe_worker.py -> FastAPI routes`

该链路下前端不会直接访问 `http://127.0.0.1:8000`，但后端 HTTP 路由与 SSE 协议保持不变（worker 在进程内复用同一套路由实现）。
