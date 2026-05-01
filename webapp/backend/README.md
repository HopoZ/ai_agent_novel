# `webapp/backend` — File Responsibilities

FastAPI backend layer: HTTP routes, request validation, SSE, and glue logic to `agents`.

For **overall architecture, primary flow, graph/lore behavior, and integration checklist**,
see [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md).  
Frontend project guide: [`../frontend/README.md`](../frontend/README.md).  
Static/templates: `webapp/static/`, `webapp/templates/`; frontend build output: `webapp/frontend/dist/`.

---

## Run

From the **repository root**:

```bash
python -m uvicorn webapp.backend.server:app --reload --port 8000
```

| Environment Variable | Purpose |
|----------------------|---------|
| `SKIP_FRONTEND_BUILD=1` | Skip backend-start `npm run build` and use existing `dist/` only |

---

## Files and `routes/`

| Path | Responsibility |
|------|----------------|
| `README.md` | This file |
| `__init__.py` | Package marker |
| `server.py` | ASGI import target: exports `app`, `create_app`; test alias `_infer_time_slot` |
| `app.py` | `create_app()`: CORS, request logging middleware, `/static`, mounts sub-routers, optional frontend build at startup |
| `deps.py` | Singleton `NovelAgent`, named logger |
| `paths.py` | Path constants relative to repo root (Vite, `storage/novels`, etc.) |
| `schemas.py` | Pydantic request/response models (`RunModeRequest` fields `structure_card` / `structure_risk_ack` / `shadow_director_guidance`, `ApiModelListRequest.force_refresh`, `CreateNovelRequest.auto_generate_lore/auto_lore_brief`, and graph `Graph*`) |
| `frontend_assets.py` | `dist` freshness checks, `npm build`, mounts `/assets` |
| `sse.py` | SSE frame wrappers for `run_stream` |
| `run_helpers.py` | Time-slot inference, `user_task` composition, chapter-event helpers, pre-write graph skeleton; includes shadow-director guidance injection; **no** FastAPI dependency |
| `domain/README.md` | Domain-rules directory notes (new in this round) |
| `domain/novel_lore_tags.py` | Novel lore-tag scoping and normalization rules (moved from `routes/novels.py`) |
| `services/README.md` | Service-orchestration directory notes (new in this round) |
| `services/auto_lore.py` | Auto-lore build/rewrite/atomic write/manifest logic (moved from `routes/novels.py`) |
| `services/novel_run.py` | Shared run flow logic (event binding validation, error-code inference, plan payload unwrapping) |
| `graph_payload.py` | Build read-only `GET /graph` nodes/edges JSON from `state` + four graph tables |
| `routes/__init__.py` | Routes package |
| `routes/README.md` | Routing boundary notes (thin-route convention) |
| `routes/pages.py` | `GET /`: Vite `index.html` or legacy template fallback |
| `routes/settings.py` | `/api/settings`, `/api/settings/api_key`, `/api/settings/models`, `/api/settings/test_connection` (LLM provider config, model list, connectivity test; backend TTL cache + `force_refresh`, returns `model_items.capabilities`) |
| `routes/lore.py` | `/api/lore/*`: `POST summary/build`, `GET summary/{id}`, `GET tags`, `GET preview`; plus tag file management: `POST/PATCH/DELETE /tags`, `PUT /tags/content`, `POST /tags/batch_delete`, `POST /tags/batch_replace_prefix` (bulk operations also sync bound `lore_tags`) |
| `routes/novels.py` | `/api/novels/*`: list/create/`state`/`character_entities`/chapter `chapters/{i}`/`anchors`/`run`/`preview_input`/`run_stream`; supports auto-lore generation on create, `/auto_lore` query and `/auto_lore/regenerate`; writing flow includes structure gate `structure_gate`, shadow-director policy `shadow_director` (auto detail takeover + undo), post-write `consistency_audit` (high-risk blocks like timeline reversal, character teleportation, unsupported relation jumps); streaming planning supports `ChapterPlan/result/output` wrappers; chapter outputs saved per-novel directory |
| `routes/graph.py` | `/api/novels/{id}/graph` (GET), plus `PATCH graph/node`, `POST graph/nodes`, `DELETE graph/nodes`, `POST graph/relationship`, `PATCH timeline-neighbors`, `PATCH graph/edge` |
