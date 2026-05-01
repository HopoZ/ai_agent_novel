# AI Novel Agent（中文）

一个长篇小说写作助手，支持 Web、CLI 和 Electron 桌面版。

English: [`README.md`](./README.md)

## 快速开始(CLI、Web、Exe三种任选一种)

### CLI



#### 1）安装依赖

```bash
pip install -r requirements.txt
```

#### 2）配置 API Key

打开 Web 界面右上角 API 设置，保存以下配置：

- DeepSeek：API Key
- OpenAI Compatible：API Key + Base URL + Model

#### 3）准备设定

把 Markdown 设定文件放到 `lores/` 目录。

#### 4）启动

```bash
python -m cli
```
### Web

```bash
python -m uvicorn webapp.backend.server:app --reload --port 8000
```

浏览器访问：`http://127.0.0.1:8000/`

### Exe

下载发布包：<https://github.com/HopoZ/ai_agent_novel/releases>

## Electron 调试模式

如果安装后应用无法打开或闪退，请使用调试模式。

- 环境变量开启：`NOVEL_AGENT_ELECTRON_DEBUG=1`
- 或启动参数开启：`--debug-electron`
- 调试模式下会：
  - 自动打开 DevTools
  - 弹出启动健康检查信息
  - 主进程和后端日志写入：
    - `%APPDATA%/AI Novel Agent/logs/electron-main.log`（Windows）


## 许可证

AGPL-3.0-or-later，见 [`LICENSE`](./LICENSE)。
