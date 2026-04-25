# `webapp/backend/domain` 目录说明

本目录用于放后端领域规则（纯规则优先，弱依赖框架）。

## 文件职责

- `novel_lore_tags.py`（本次新增）
  - lore tag 标准化
  - 自动设定 tag 的小说作用域过滤
  - 合并/去重规则（保留当前小说 auto tags，剔除其他小说 auto tags）

## 约定

- 领域层应尽量保持“可独立测试”的纯函数形态。
- 不处理 HTTP 协议细节，不直接依赖 FastAPI。

