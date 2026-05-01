# AI Novel Agent

An engineering-oriented writing system for long-form web fiction and serialized narratives.
It uses Markdown files under `lores/` as world-setting sources, and builds an iterative
creation loop with **plan -> write -> state update -> persistence**.

It provides a **FastAPI + Vue 3** web workspace (input preview, SSE streaming output,
knowledge-graph editing), plus optional CLI and Flet mobile examples.

Chinese version: [`README_ch.md`](./README_ch.md)

**Preview**

| Web Workspace | Knowledge Graph |
|--------------|-----------------|
| See `images/` preview assets | See `images/` preview assets |

---

## Tech Stack

| Layer | Technology |
|------|------------|
| Frontend | Vue 3, TypeScript, Vite, Element Plus, ECharts, optional Electron shell |
| Backend | Python 3, FastAPI, LangChain (DeepSeek + OpenAI-compatible API) |
| Domain | `NovelAgent`, state compaction/merge, four-table graph persistence, lore summary cache |

---

## Quick Start

### 1) Install Dependencies

```bash
pip install -r requirements.txt
```

### 2) Configure API Keys

Configure and save in the web UI top-right **API Key** dialog
(stored locally in `storage/user_settings.json`):

- `DeepSeek`: API Key
- `OpenAI Compatible`: API Key + Base URL + Model

This project now primarily follows frontend/Electron local settings,
instead of relying on environment-variable priority.

### 3) Prepare Lore

Place Markdown lore files under `lores/`.
Relative paths become tag namespaces for selection and injection.

### Start (choose one)

#### Run Web App

From the **repository root**:

```bash
python -m uvicorn webapp.backend.server:app --reload --port 8000
```

Open: `http://127.0.0.1:8000/`

- Startup attempts frontend build (`webapp/frontend` -> `dist/`).
  To skip: set `SKIP_FRONTEND_BUILD=1`.
- Frontend-only development:
  `cd webapp/frontend && npm install && npm run dev`
  (proxy and ports from `vite.config.ts`).

#### Run CLI

Uses multi-turn dialogue + raw lore injection without the web state machine:

```bash
python -m cli
```

Default model is DeepSeek reasoning (`deepseek-reasoner`).
Terminal streaming separates "reasoning" and "final text";
session files keep final text only for API compatibility.
Use `--fast` for `deepseek-chat`.

#### Electron Desktop Shell

[Download releases](https://github.com/HopoZ/ai_agent_novel/releases)

---

## Feature Highlights

- **Preview before run**: main flow calls `preview_input` first, then `run_stream` after confirmation.
- **Streaming and cancelable**: planning/body/optimization SSE phases are observable and interruptible.
- **Shadow director (light-touch)**: suggests event bindings during pre-input; one-click apply with safe fallback.
- **Structure-card gate (pre-write constraint)**: auto-fill and lock structure cards (goal/conflict/turning point/foreshadow recovery/event ownership); requires risky-continue confirmation if minimum fields are missing.
- **Consistency audit v2 (blockable)**: returns score/issues/block reasons/fix actions after writing; includes high-risk rules (timeline reversal, character teleportation, unsupported relation jumps), and can block auto "continue next chapter".
- **Inline next-chapter writing**: edit and generate next chapter directly in right-side suggestion panel, reusing the same preview chain and auto-binding timeline context when possible.
- **Shadow director v2 (auto-detail takeover)**: recommends side characters/conflict styles/foreshadow strategy; auto-applies by default and supports one-click undo.
- **Auto-lore pack on create**: creating a novel can generate drafts under an auto-generated lore subfolder in `lores/<...>/<novel_id>/` (world skeleton, character relations, mainline foreshadowing), viewable/regenerable from UI.
- **Built-in tag management (with bulk ops)**: create/rename/delete/edit tags in left panel; supports bulk delete and prefix migration, syncing bound `lore_tags`.
- **Advanced graph management**: character/event/mixed views; full-screen node/edge editing; type filters, isolated-node checks, hit-count search, auto-focus on create, JSON snapshot export (from `storage/novels/<id>/novel.db` and `novel_state`).
- **Enhanced graph interactions**: right-drag edge creation (character relation / timeline progression / appearance / chapter ownership); event graph auto-orders horizontally by `timeline_next`; supports chapter expand by selected event and expand/collapse all.
- **Advanced-operations drawer**: batch edge deletion moved to secondary drawer to reduce main-panel clutter.
- **Model provider UX improvements (v1)**: OpenAI-compatible model list has backend TTL + frontend session cache, force refresh, and capability labels (`chat` / `vision` / `tool` / `reasoning`).
- **Frontend directing workspace**: middle panel is now a single-screen workspace (manual Step1~4 flow with next-step highlighting, hide non-current steps by default, next/prev controls), run output moved to drawer; graph supports compact slice + full-screen studio; Step3 can auto-draft tasks when empty.

---

## Run Modes (`RunModeRequest.mode`)

| Mode | Description |
|------|-------------|
| `init_state` | Initialize world state (required before writing) |
| `plan_only` | Chapter planning only + state update |
| `write_chapter` | Plan + write body + persist |
| `revise_chapter` | Revise mode (reuses planning + writing chain) |
| `expand_chapter` | Expand mode (`expand` in writing phase) |
| `optimize_suggestions` | Optimization suggestions (independent chain, not main chapter persistence chain) |

---

## Repository Structure (Brief)

```text
agents/              # Domain: NovelAgent, state, prompts, persistence, lore
webapp/backend/      # FastAPI: routes, SSE, schemas, run_helpers, graph_payload
webapp/frontend/     # Vue 3 workspace source
lores/               # Lore Markdown files (commit policy depends on .gitignore)
storage/             # Runtime data, summary cache, per-novel directories
outputs/             # Chapter output archive, per novel
cli.py               # Terminal entry
electron/            # Electron shell (uvicorn subprocess + windows)
mobile/              # Flet client example
```

---

## Data and API (Summary)

Persistence essentials:

- **Per-novel data**: `storage/novels/<id>/novel.db`
  (SQLite: `novel_state`, chapter rows, four graph tables)
- **Runtime narrative state**: `NovelState` JSON in `novel_state`
  (relationship edges are sourced from the four graph tables)
- **Graph**: character/event entities and relations stored in the same DB,
  mapped to `GET/PATCH/POST/DELETE /api/novels/{id}/graph*`

Common HTTP examples:

- `POST /api/lore/summary/build`, `GET /api/lore/tags`, `GET /api/lore/preview`
- `POST /api/novels/{id}/preview_input`, `POST /api/novels/{id}/run_stream` (SSE)
- `POST /api/novels/{id}/run` (non-streaming JSON)

For complete fields and behavior, treat code as source of truth:
`webapp/backend/schemas.py`, `agents/`, and docs under `storage/` when present.

---

## Design Principles (Brief)

- **Continuity**: state-machine driven, not single-shot generation.
- **Controllable lore**: tag-based lore + summary cache + raw fallback on misses.
- **Observability**: phase events, token hints, and previewable inputs.
- **Robustness**: structured output and merge strategy to reduce long-output failure cost.

Practical suggestion: build summaries for frequently used tags first, then write by chapter;
treat graph relations as source of truth before generation.

---

## Roadmap

See [TOURMAP.md](./TOURMAP.md) for progress and plans.

---

## License and Author

- **License**: AGPL-3.0-or-later, see [LICENSE](./LICENSE).
- **Author**: see [NOTICE](./NOTICE).
