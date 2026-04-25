# `webapp/backend/routes` 目录说明

本目录是 FastAPI 路由层。重构后目标是“薄路由”：负责 HTTP 入参校验、错误码映射、调用 service/domain。

## 文件职责

- `novels.py`
  - 小说主流程路由（创建、运行、SSE、事件计划等）。
  - 本次已把 lore tag 规则、auto-lore 构建与部分运行共用逻辑下沉到 `../domain` 和 `../services`。
- `graph.py`
  - 图谱相关 API（节点/边 CRUD、关系处理）。
- `lore.py`
  - 标签、摘要、预览与批量 tag 管理。
- `settings.py`
  - 模型配置、连通性检测、模型列表。
- `pages.py`
  - 页面入口与回退。

## 路由层约定

- 路由内尽量不写复杂业务规则，优先调用 `services/*`。
- 领域规则统一放 `../domain/*`。
- 对外响应结构和错误文案保持兼容，拆分时优先“委托而非改协议”。

## 事件计划专门流程约定

- `novels.py` 中写作相关入口（`/run`、`/preview_input`、`/run_stream`）必须执行：
  1) 先校验 `existing_event_id` 绑定；  
  2) 再校验该事件存在 `event_plan`；  
  3) 通过后才允许写作链路继续。
- SSE 错误码与 HTTP 拒绝文案要保持同一语义（缺绑定 / 缺计划）。
- 路由不自行兜底“自动补计划”，避免绕过 event-only 流程约束。

