# `webapp/backend/services` 目录说明

本目录承载后端“业务编排服务”，用于承接从 `routes` 下沉的可复用逻辑。

## 文件职责

- `auto_lore.py`（本次新增）
  - 自动设定文件模板构建
  - 图谱引导重写入口
  - 文件名规范化与约束校验
  - 原子写入与 manifest 读写
- `novel_run.py`（本次新增）
  - `run` 流程共用方法：事件绑定校验、错误码推断、EventPlan -> ChapterPlan 转换、payload 解包

## 设计意图

- 减少 `routes/novels.py` 内部“控制器 + 业务 + 持久化细节”耦合。
- 提供可单测的函数边界，降低后续功能扩展风险。

## 维护约定

- service 可依赖 `agents/*` 与 `persistence/*`，但尽量不依赖 FastAPI 对象。
- 对外暴露函数优先保持明确输入输出，不读全局请求上下文。

