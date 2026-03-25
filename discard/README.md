这里是项目的“丢弃/归档”目录。

放入原则：
- 已被新架构替代（例如旧版前端静态页、旧版脚本示例）
- 空占位文件（未被当前 Web 后端/前端引用）
- 临时测试脚本（不再作为主流程的一部分）

当前主流程（仍在使用）：
- 后端 API：`webapp/server.py`
- 核心引擎：`agents/novel_agent.py`、`agents/state_models.py`、`agents/storage.py`、`agents/loader.py`
- 前端（Vite/Vue）：`webapp/frontend/src/*`（build 到 `webapp/frontend/dist` 并由后端托管）

