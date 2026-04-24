# `webapp/frontend` — 各文件职责

Vue 3 + TypeScript + Vite；UI 为 Element Plus；图谱为 ECharts。构建输出目录 `dist/`，由后端 [`../backend/frontend_assets.py`](../backend/frontend_assets.py) 挂载。

**产品流程、REST/SSE 摘要、字段联调**见 [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md)。  
后端各 Python 文件列表见 [`../backend/README.md`](../backend/README.md)。

---

## 命令

| 命令 | 作用 |
|------|------|
| `npm install` | 安装依赖 |
| `npm run dev` | 开发服务器（代理以后端/Vite 配置为准） |
| `npm run build` | 生产构建 → `dist/` |
| `npm run preview` | 预览构建结果 |

后端可用环境变量 `SKIP_FRONTEND_BUILD=1` 跳过自动构建。

---

## 根与配置

| 路径 | 作用 |
|------|------|
| `README.md` | 本文件 |
| `package.json` | 依赖与脚本 |
| `vite.config.ts` | Vite 配置 |
| `index.html` | HTML 壳、页面标题、Noto Serif SC 字体链接 |
| `dist/` | 构建输出（通常不入库） |

---

## `src/`

| 路径 | 作用 |
|------|------|
| `main.ts` | 入口：Vue、Element Plus、`theme-literary.css` |
| `theme-literary.css` | 全局文学暖色主题（纸感背景、Element 变量、卡片/弹窗/顶栏等） |
| `App.vue` | 根布局：左栏上下文 + 中栏导演工作台，运行结果改为抽屉；含影子编导自动细节接管（可撤销）、一致性审计阻断续写、结构卡风险确认，以及“自动设定管理”（查看/重生成创建时自动 lores 草案）和 Tag 内置管理（单条 + 批量删除/批量前缀迁移） |
| `api/client.ts` | `apiJson`、`apiSse`（`run_stream` 解析）、`logDebug` |
| `composables/usePanelResize.ts` | 左/中栏拖拽宽度；窗口变窄时压缩左/中避免溢出；`layoutStacked`（≤1180px 三栏纵向堆叠，隐藏分割条） |
| `composables/useGraph.ts` | ECharts 实例、拉取/刷新图、节点边编辑 API、`GRAPH_INJECTION_KEY` |
| `components/TagPanel.vue` | 左栏：设定标签树、摘要、批量勾选、本书 tags 同步，以及内置 Tag 管理入口（新建/重命名/删除/编辑内容） |
| `components/MidFormPanel.vue` | 中栏导演工作台：Step1~Step4 自动流转；非当前步骤默认隐藏；支持“下一步/上一步”和当前步骤状态条 |
| `components/RightPanel.vue` | 运行面板主体（被 `App.vue` 放入 Drawer），展示阶段/token/正文/下章建议/规划流/图谱入口 |
| `components/dialogs/TextPreviewDialog.vue` | 通用长文本预览 |
| `components/dialogs/CreateNovelDialog.vue` | 新建小说（支持创建时自动生成 lores 设定草案与补充说明） |
| `components/dialogs/InputPreviewDialog.vue` | 分阶段 Input 预览 + 结构卡展示 + 风险续写确认 |
| `components/dialogs/NextChapterHintDialog.vue` | 下章提示 → 写入任务再走预览链 |
| `components/dialogs/RoleManagerDialog.vue` | 会话内角色标签 |
| `components/dialogs/ApiSettingsDialog.vue` | LLM 提供商配置（DeepSeek / OpenAI 兼容）；模型列表会话缓存 + 后端 TTL 命中提示、强制刷新入口、能力标签展示；保存前连通性测试 |
| `components/graph/GraphSliceCard.vue` | 中栏轻量图谱切片（节点/边统计、当前事件上下文、进入全屏工作室入口） |
| `components/graph/GraphDialogs.vue` | 全屏图谱、侧栏编辑；`inject(GRAPH_INJECTION_KEY)` |
| `counter.ts` | Vite 默认示例（计数器），`main.ts` 未使用，可删 |
| `style.css` | Vite 默认全局样式，当前主界面以 `theme-literary.css` 与 Element 为主 |
| `assets/*.svg` | 模板资源，主应用未引用 |

---

## 技术备注（文件级）

- `apiSse` 的事件名与 payload 须与后端 `run_stream` 一致（含 `done.consistency_audit`、`done.structure_gate`、`done.shadow_director`）。
- `useGraph` 在卸载时 `dispose` 图表并移除 `resize` 监听。
- TypeScript：`apiJson` 返回 `unknown` 时在调用处收窄类型。
