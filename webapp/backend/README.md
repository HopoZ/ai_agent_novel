# `webapp/backend` — 各文件职责

FastAPI 后端：HTTP 路由、请求体验证、SSE、与 `agents` 之间的胶水层。

**整体架构、主链路、图谱/Lore 行为、联调清单**见 [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md)。  
前端工程见 [`../frontend/README.md`](../frontend/README.md)。  
静态与模板：`webapp/static/`、`webapp/templates/`；前端构建产物：`webapp/frontend/dist/`。

---

## 运行

在**仓库根目录**：

```bash
python -m uvicorn webapp.backend.server:app --reload --port 8000
```

| 环境变量 | 作用 |
|----------|------|
| `SKIP_FRONTEND_BUILD=1` | 跳过后端启动时的 `npm run build`，仅用已有 `dist/` |

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
| `schemas.py` | Pydantic 请求/响应模型（含 `RunModeRequest`、图谱 `Graph*` 等） |
| `frontend_assets.py` | `dist` 新鲜度、`npm build`、挂载 `/assets` |
| `sse.py` | `run_stream` 的 SSE 帧封装 |
| `run_helpers.py` | 时间段推导、`user_task` 拼接、章节-事件辅助、写前图骨架；**无** FastAPI 依赖 |
| `graph_payload.py` | 由 `state` + 四表拼装 `GET /graph` 的 nodes/edges JSON（只读） |
| `routes/__init__.py` | 路由包 |
| `routes/pages.py` | `GET /`：Vite `index.html` 或旧模板回退 |
| `routes/settings.py` | `/api/settings`、`/api/settings/api_key`、`/api/settings/models`、`/api/settings/test_connection`（LLM 提供商配置、模型列表、连通性测试） |
| `routes/lore.py` | `/api/lore/*`：`POST summary/build`、`GET summary/{id}`、`GET tags`、`GET preview` |
| `routes/novels.py` | `/api/novels/*`：列表、创建、`state`、`character_entities`、按章 `chapters/{i}`、`anchors`、`run`、`preview_input`、`run_stream`；写作模式含结构卡门禁 `structure_gate`（自动锁定 + 风险确认）与写后 `consistency_audit` |
| `routes/graph.py` | `/api/novels/{id}/graph`（GET）；`PATCH graph/node`、`POST graph/nodes`、`DELETE graph/nodes`、`POST graph/relationship`、`PATCH timeline-neighbors`、`PATCH graph/edge` |
