# AI Novel Agent（中文说明）

面向长篇网文/系列叙事的工程化写作系统。  
项目基于 `lores/` 设定库，形成 **plan -> write -> state update -> persistence** 的可迭代创作闭环。

- Web 工作台：FastAPI + Vue 3（Input 预览、SSE 流式输出、图谱编辑）
- 可选形态：CLI、Electron 桌面端

> English version: [`README.md`](./README.md)

## 快速开始

### 1) 安装依赖

```bash
pip install -r requirements.txt
```

### 2) 配置 API 密钥

在 Web 端右上角 API 设置中保存（写入 `storage/user_settings.json`）：

- DeepSeek：填写 API Key
- OpenAI Compatible：填写 API Key + Base URL + Model

### 3) 准备 Lore

将 Markdown 设定放入 `lores/`（相对路径会作为标签空间）。

### 4) 启动方式（三选一）

#### Web

```bash
python -m uvicorn webapp.backend.server:app --reload --port 8000
```

浏览器访问：`http://127.0.0.1:8000/`

#### CLI

```bash
python -m cli
```

#### Electron

发布包见：<https://github.com/HopoZ/ai_agent_novel/releases>

## 常用目录

```text
agents/              # NovelAgent、状态、提示词、持久化、Lore
webapp/backend/      # FastAPI 后端
webapp/frontend/     # Vue 3 前端
lores/               # 设定 Markdown
storage/             # 运行时数据（按小说分目录）
outputs/             # 章节输出归档（按小说分目录）
electron/            # Electron 桌面壳
```

## 许可证

AGPL-3.0-or-later，详见 [`LICENSE`](./LICENSE)。
