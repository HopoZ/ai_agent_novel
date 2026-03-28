# 前端说明（`webapp/frontend`）

本目录为小说创作 Web UI：**Vue 3 + TypeScript + Vite**，UI 为 **Element Plus**，图谱为 **ECharts**。构建产物输出到 `dist/`，由 FastAPI 挂载（见 **`../backend/frontend_assets.py`**）。

**文档分工**：界面与前端工程见**本文件**；启动命令、REST/SSE、图谱 API 摘要见 **`../backend/README.md`**。

---

## 1. 命令

| 命令 | 说明 |
|------|------|
| `npm install` | 安装依赖 |
| `npm run dev` | 开发服务器（默认与后端同源或按 Vite 配置代理） |
| `npm run build` | 生产构建 → `dist/` |
| `npm run preview` | 本地预览构建结果 |

环境变量 `SKIP_FRONTEND_BUILD=1` 可让后端跳过自动构建（仅使用已有 `dist/`）。

---

## 2. 目录结构

```text
webapp/frontend/
├── README.md                 # 本文件：前端总览
├── package.json
├── vite.config.ts
├── index.html
├── dist/                     # 构建输出（通常不入库）
└── src/
    ├── main.ts               # 入口：Element Plus 全局注册、挂载 App
    ├── App.vue               # 根布局：三栏、小说/标签/锚点/角色状态、运行与 SSE、provide 图谱
    ├── api/
    │   └── client.ts         # apiJson（JSON API）、apiSse（run_stream 解析）、logDebug
    ├── composables/
    │   ├── usePanelResize.ts # 左/中栏拖拽宽度与卸载时解绑
    │   └── useGraph.ts       # 图谱：ECharts、拉数、节点/边编辑 API；GRAPH_INJECTION_KEY
    └── components/
        ├── TagPanel.vue      # 左栏：设定标签树、摘要预览、批量勾选
        ├── MidFormPanel.vue  # 中栏：小说/时序/角色/任务/运行与中止
        ├── RightPanel.vue    # 右栏：SSE 输出、规划流、下章建议、图谱入口
        ├── dialogs/
        │   ├── TextPreviewDialog.vue   # 通用长文本预览（如 tag 摘要）
        │   ├── CreateNovelDialog.vue   # 创建新小说
        │   ├── InputPreviewDialog.vue  # 模型分阶段 Input 预览 + 确认运行
        │   └── RoleManagerDialog.vue   # 会话内角色标签增删
        └── graph/
            └── GraphDialogs.vue        # 全屏图谱、新建节点、侧栏编辑（inject 图谱控制器）
```

---

## 3. 组件职责摘要

- **TagPanel**  
  只通过 props 接收数据与回调，不单独持有业务真源。标签格式与后端 `settings/**/*.md` 路径 tag 一致。

- **MidFormPanel**  
  表单字段绑定父级 `form`；运行按钮触发预览链路；折叠分区状态由 `App.vue` 的 `midActiveSections` 双向同步。

- **RightPanel**  
  展示运行阶段、token 提示、outputs 路径；图谱 Tab 仅提供「打开全屏」，画布不在此挂载。

- **dialogs/**  
  弹窗级 UI，尽量用 `defineModel` 与父级同步可见性；具体请求仍在 `App.vue`（或后续 composable）中发起。

- **GraphDialogs**  
  通过 `inject(GRAPH_INJECTION_KEY)` 使用 `useGraph()` 返回的响应式对象（含 `loadGraph`、`openGraphDialog` 等）。  
  `App.vue` 中：`useGraph(toRef(form, 'novelId'))` + `provide(GRAPH_INJECTION_KEY, graph)`。  
  运行结束后若全屏图谱已开或当前在图谱 Tab，由 `App.vue` 的 `executeRun` 调用 `graph.loadGraph()` 刷新。

---

## 4. 主要功能（产品视角）

- 小说列表选择、创建新小说（带 lore tag 勾选）
- Lore 标签树、摘要生成、悬浮/弹窗预览
- 时间线事件：归属已有事件或新建事件（前后继可选）
- 主视角 / 配角多选、角色标签会话管理
- **Input 预览** → 确认后 **SSE `run_stream`**：规划流、正文流式、保存阶段、outputs 路径、下章建议
- Token 用量展示、手动中止运行
- 三栏宽度可拖拽（左—中、中—右）
- 全屏图谱：人物 / 事件 / 混合视图，节点与边编辑（API 在 `webapp/backend/routes/graph.py`，说明见 `../backend/README.md`）
- 手动时间段等选项与后端「最小状态注入」策略一致（详见根目录 README 与后端注释）

---

## 5. 与后端联调清单

修改请求体或字段名时，请同步核对：

- `webapp/backend/schemas.py`
- `webapp/backend/routes/*.py`（按领域拆分路由）
- `agents/novel/novel_agent.py`（若涉及 Agent 参数）

修改标签或摘要相关 UI 时，核对：

- `GET /api/lore/preview`
- `POST /api/lore/summary/build`
- `GET /api/lore/tags`

修改图谱交互或字段时，核对：

- `GET/PATCH/POST/DELETE /api/novels/{id}/graph/*`（见 `webapp/backend/routes/graph.py`）

组件 props 与回调命名变更时：

- **MidFormPanel / RightPanel**：父组件传参需一并改；避免在子组件上对 props 使用非法 `v-model`（宜用 `model-value` + `update:*` 或回调 props，与现有一致）。

---

## 6. 技术备注

- TypeScript 严格程度以 `tsconfig` / Vite 为准；`apiJson` 返回值为 `unknown` 时在调用处收窄类型。
- SSE 解析逻辑在 `api/client.ts` 的 `apiSse`；事件名与 payload 形状须与 `run_stream` 实现一致。
- ECharts 实例在 `useGraph` 内创建，组件卸载时 `dispose` 并移除 `resize` 监听。
