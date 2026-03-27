## AI Novel Agent

A lore-driven, stateful long-form fiction generation system.  
It uses `settings/*.md` as SSOT and runs a stable loop: `plan -> write -> state update -> persist`, with Web streaming, prompt observability, and graph visualization.

## Core Capabilities

- **Stateful writing loop**: persist characters, world, timeline, and continuity in `NovelState`
- **SSE streaming**: `planning/auto_init/writing/saving/done`
- **Structured fault tolerance**: JSON repair + `next_state` patch merge
- **Lore summary pipeline**:
  - LLM-generated summaries (no rule-based extraction)
  - per-tag cache (`llm_tag_v1`)
  - automatic raw-lore fallback on cache miss
- **Prompt observability**: inspect actual assembled input via `/preview_input`
- **Graph views**: `people / events / mixed`
- **Token visibility**: frontend displays token usage for auto-init and chapter generation

## Run Modes

| Mode | Description |
|---|---|
| `init_state` | Initialize world state |
| `plan_only` | Generate chapter plan and update state only |
| `write_chapter` | Plan + write + persist |
| `revise_chapter` | Revision mode (currently follows plan+write flow) |

## Lore and Context Strategy

### Lore injection
- Runtime uses `lore_tags` (no `lore_summary_id` dependency)
- Each tag tries summary cache first, then falls back to raw markdown
- "Generate current tag summaries" actively regenerates for selected tags
- Summary API returns `tag_summaries: [{ tag, summary }]`

### Chapter context
- Inject only two neighboring relevant chapters by default
- If `time_slot_override` is set manually, chapter JSON context is skipped
- Chapter JSON `content` is excluded from core context to reduce token load

### Hover preview
- `compact=1` shows summary preview for the tag
- If no cache exists, UI prompts user to generate summary first

## Architecture

```text
[Presentation]
Vue3 + Element Plus + ECharts
        |
        v
[API]
FastAPI (webapp/server.py)
  - /api/novels/*
  - /api/lore/*
  - /api/novels/*/graph
  - /api/novels/*/run_stream
        |
        v
[Domain]
NovelAgent (agents/novel_agent.py)
  - build_lore_summary_llm
  - plan_chapter / write_chapter_text
  - merge_state
  - preview_input
        |
        v
[Data]
settings/*.md
storage/lore_summaries/*.json
storage/novels/<id>/{state.json, chapters/*.json}
outputs/*.txt
```

## Quick Start

### 1) Install
```bash
pip install -r requirements.txt
```

### 2) Configure API key
Create `.env` in project root:
```bash
DEEPSEEK_API_KEY=<your_api_key>
```

### 3) Prepare lore files
Put markdown lore files under `settings/`.

### 4) Run server
```bash
python -m uvicorn webapp.server:app --reload --port 8000
```
Open: `http://127.0.0.1:8000/`

## Common Issue

### WinError 2 (`npm` not found on startup)
Cause: uvicorn process PATH may differ from your interactive terminal PATH.  
Current behavior: on Windows, startup build prefers `npm.cmd`; if unavailable, server logs a warning and skips auto frontend build.

## License

- AGPL-3.0-or-later (`LICENSE`)
- Author info in `NOTICE`

