# `webapp/frontend/src` 目录说明

本目录在本次重构后按“壳层组件 + 组合式逻辑 + 领域纯函数”分层，避免 `App.vue` 继续膨胀。

## 分层约定

- `App.vue`
  - 负责页面装配、组件编排、主题切换、少量胶水逻辑。
  - 避免继续新增“纯计算/纯规则/可复用状态机”逻辑。
- `composables/`
  - 放可复用的状态与行为逻辑（运行态格式化、表单模型、标签树操作等）。
- `domain/`
  - 放纯函数与领域规则（无 UI、无网络副作用）。
- `components/`
  - 以展示和交互为主，尽量通过 props/emits 调用外层逻辑。
- `api/`
  - 网络通信适配层（`apiJson` / `apiSse`）。

## 本次重构落点

- 从 `App.vue` 抽出：
  - `composables/useNovelRun.ts`
  - `composables/useNovelsAndForm.ts`
  - `composables/useLoreTags.ts`
  - `domain/tags.ts`

## 维护建议

- 新增逻辑优先判断是否可放入 `composables` / `domain`，避免回流到 `App.vue`。
- 组件内重复样式优先走 `theme-literary.css` token，不新增硬编码颜色。

## 事件计划专门流程（前端约定）

- 工作台按固定顺序引导：`选已有事件` -> `生成/重生成事件计划` -> `预览` -> `运行`。
- `App.vue` 负责在提交 `preview_input` / `run` 前做轻门禁（无绑定、无事件计划时前端直接拦截）。
- 最终门禁以后端为准；前端只做可用性提示，不替代服务端约束。

