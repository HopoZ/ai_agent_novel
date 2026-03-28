# `webapp/backend` — FastAPI 后端

本目录为小说创作 Web 服务的**后端 Python**：路由按领域拆分，运行辅助与图谱拼装独立成模块，便于维护与单测。

**文档分工**：HTTP/API/运行方式见**本文件**；前端工程见 **`../frontend/README.md`**。

模板与静态文件在 **`webapp/templates`**、**`webapp/static`**；前端源码与 `dist` 在 **`webapp/frontend/`**。

---

## 目录结构

```text
webapp/backend/
├── README.md           # 本文件
├── __init__.py
├── server.py           # ASGI 入口：导出 app、create_app、测试用 _infer_time_slot
├── app.py              # create_app()：CORS、日志中间件、静态资源、挂载子路由、启动时前端构建
├── deps.py             # 单例 NovelAgent、命名 logger
├── paths.py            # 相对仓库根的路径常量（Vite、storage/novels 等）
├── schemas.py          # 全部 Pydantic 请求体（含图谱 Graph* 模型）
├── frontend_assets.py  # dist 过期检测、npm build、挂载 /assets
├── sse.py              # run_stream 的 SSE 帧封装
├── run_helpers.py      # 时间段推导、user_task 拼接、章节-事件绑定、写前预构建图谱四表骨架（无 FastAPI）
├── graph_payload.py    # 由 state + 四表生成 GET /graph 的 nodes/edges JSON
└── routes/
    ├── pages.py        # GET /  → Vite index 或旧模板
    ├── lore.py         # /api/lore/*（tags、preview、summary）
    ├── novels.py       # /api/novels/*（列表、创建、state、章节、锚点、run、preview_input、run_stream）
    └── graph.py        # /api/novels/{id}/graph*（读图与节点/边/时间线编辑）
```

---

## 文件职责摘要

| 模块 | 职责 |
|------|------|
| `app.py` | 组装 `FastAPI` 实例；不要在此写业务分支 |
| `server.py` | `uvicorn webapp.backend.server:app` 的导入目标；薄封装 |
| `routes/*` | 仅 HTTP 层：取参、调 `agent` / `run_helpers` / `graph_payload`、抛 `HTTPException` |
| `run_helpers.py` | 与 `RunModeRequest` 相关的纯函数，可被测试直接引用（`infer_time_slot` 等） |
| `graph_payload.py` | 图谱可视化数据结构，与 `routes/graph.py` 的写操作分离 |
| `schemas.py` | 请求体验证；改字段时同步路由与前端 |

---

## 运行方式

在**仓库根目录**执行：

```bash
python -m uvicorn webapp.backend.server:app --reload --port 8000
```

环境变量 **`SKIP_FRONTEND_BUILD=1`**：跳过启动时的自动 `npm run build`。

---

## `webapp/` 布局（上下文）

```text
webapp/
├── backend/           # 本目录
├── frontend/          # Vue/Vite（说明见 frontend/README.md）
├── templates/         # 回退入口 HTML
└── static/            # 静态资源
```

领域逻辑在 **`agents/`**。

---

## 核心接口（摘要）

- `POST /api/novels/{novel_id}/preview_input`、`POST .../run_stream`（SSE）
- `GET /api/novels/{novel_id}/graph` 及 `PATCH .../graph/node|edge` 等（详见 `routes/graph.py`）
- `GET/POST /api/lore/*`（详见 `routes/lore.py`）

### SSE（`run_stream`）

- `phase=outputs_written` / `outputs_write_failed` 等与原先一致

### 手动时间线注入

- 逻辑仍在 `agents` 与 `RunModeRequest` 字段；路由层只透传 `infer_time_slot`、`manual_time_slot` 等

---

## 修改时的联动清单

- 改 **`schemas.py`**：同步相关 `routes/*.py`、`../frontend` payload、`agents/novel/novel_agent.py`
- 改 **运行前骨架 / 时间段推导**：优先改 `run_helpers.py`，并跑 `tests/test_time_slot_infer.py`
- 改 **图谱 JSON 形状**：`graph_payload.py` + 前端 `useGraph.ts`
- 改 **`frontend_assets.py`**：注意 Windows `npm.cmd`；与根目录 `README.md` 描述一致
