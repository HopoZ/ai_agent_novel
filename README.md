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

## License

AGPL-3.0-or-later. See [`LICENSE`](./LICENSE).
