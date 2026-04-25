# `webapp/frontend/src/composables` 目录说明

本目录承载前端“可复用状态 + 行为编排”，用于降低 `App.vue` 的复杂度。

## 文件职责

- `useGraph.ts`
  - 图谱视图状态、筛选、搜索、编辑动作与 API 交互。
- `usePanelResize.ts`
  - 左/中栏拖拽宽度与窄屏堆叠策略。
- `useNovelRun.ts`（本次新增）
  - 运行结果相关的纯格式化逻辑（审计摘要、影子导演摘要、自动重判展示文本）。
- `useNovelsAndForm.ts`（本次新增）
  - 主表单模型与默认参数常量（`DEFAULT_LLM_*`）。
- `useLoreTags.ts`（本次新增）
  - 标签树勾选/反选/全选/同步逻辑，按小说过滤标签作用域。

## 边界规范

- composable 可依赖 Vue 响应式 API。
- 纯规则优先下沉到 `../domain/`，避免 composable 变成“工具杂物箱”。
- 除 `api/client.ts` 外，尽量不要在多个 composable 内重复拼接同一 API 细节。

