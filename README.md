# AI Novel Agent

A writing assistant for long-form novels, with Web, CLI, and Electron desktop modes.

中文说明: [`README_ch.md`](./README_ch.md)

## Quick Start (choose one: CLI, Web, or Exe)

### CLI
#### 1) Install

```bash
pip install -r requirements.txt
```

#### 2) Configure API key

Open Web UI and save API settings in the top-right dialog:

- DeepSeek: API key
- OpenAI Compatible: API key + base URL + model

#### 3) Add lore files

Put your markdown setting files in `lores/`.

#### 4) Run

```bash
python -m cli
```

### Web

```bash
python -m uvicorn webapp.backend.server:app --reload --port 8000
```

Open: `http://127.0.0.1:8000/`



### Exe

Download installer from Releases: [GitHub Releases](https://github.com/HopoZ/ai_agent_novel/releases)

## Electron Debug Mode

Use debug mode when the installed app does not open, closes immediately, or cannot reach backend APIs.

- Start debug mode by any one method:
  - Launch with environment variable: `NOVEL_AGENT_ELECTRON_DEBUG=1`
  - Launch with argument: `--debug-electron`
  - In app menu: `File -> Debug Start`
- In debug mode:
  - DevTools opens automatically
  - Startup health dialog is shown (backend exe path, pid, log path)
  - Main process and backend logs are written to:
    - `<install-dir>/data/logs/electron-main.log`
- Quick troubleshooting:
  - If you see `Errno 10048`, close all app windows and relaunch once.
  - If `openPath` fails, verify `<install-dir>/data/lores` and `outputs` exist (auto-created on startup).


## License

AGPL-3.0-or-later. See [`LICENSE`](./LICENSE).
