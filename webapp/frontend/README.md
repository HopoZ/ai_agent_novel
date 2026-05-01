# `webapp/frontend` — File Responsibilities

Vue 3 + TypeScript + Vite frontend. UI uses Element Plus; graph uses ECharts.
Build output goes to `dist/`, mounted by backend
[`../backend/frontend_assets.py`](../backend/frontend_assets.py).

For **product flow, REST/SSE summary, and field-level integration notes**,
see [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md).  
For backend file mapping, see [`../backend/README.md`](../backend/README.md).

---

## Commands

| Command | Purpose |
|---------|---------|
| `npm install` | Install dependencies |
| `npm run dev` | Dev server (proxy/port follow backend and Vite config) |
| `npm run build` | Production build -> `dist/` |
| `npm run preview` | Preview built output |

Backend can set `SKIP_FRONTEND_BUILD=1` to skip auto-build.

---

## Root and Config

| Path | Purpose |
|------|---------|
| `README.md` | This file |
| `package.json` | Dependencies and scripts |
| `vite.config.ts` | Vite configuration |
| `index.html` | HTML shell, page title, Noto Serif SC font link |
| `dist/` | Build output (usually not committed) |

---

## `src/`

| Path | Purpose |
|------|---------|
| `src/README.md` | `src` layering conventions and current `App.vue` split notes |
| `main.ts` | Entry: Vue, Element Plus, `theme-literary.css` |
| `theme-literary.css` | Dual-theme tokens (tech-console / reading palette) and global semantic styles |
| `App.vue` | Root layout: left context panel + middle directing workspace, run output in drawer; includes shadow-director auto-detail takeover (undoable), consistency-audit continuation blocking, structure-card risk confirmation, auto-lore management (view/regenerate create-time lore drafts), built-in tag management (single + bulk delete/prefix replace), and inline next-chapter suggestion editing with one-click continue |
| `api/client.ts` | `apiJson`, `apiSse` (`run_stream` parsing), `logDebug` |
| `composables/README.md` | composables boundary and module notes |
| `composables/usePanelResize.ts` | Left/middle panel drag width; shrink strategy to avoid overflow on narrow windows; `layoutStacked` (<=1180px stacks 3 panels vertically and hides splitter) |
| `composables/useGraph.ts` | ECharts instance, graph fetch/refresh, node/edge edit APIs, `GRAPH_INJECTION_KEY` |
| `composables/useNovelRun.ts` | Formatting logic for run result display (audit/director/auto-retry) |
| `composables/useNovelsAndForm.ts` | Form model and default LLM parameter constants |
| `composables/useLoreTags.ts` | Tag-tree selection and novel-scoped filtering |
| `domain/README.md` | Frontend domain pure-function notes |
| `domain/tags.ts` | Tag normalization and auto-tag scoping rules (moved down from `App.vue`) |
| `components/TagPanel.vue` | Left panel: lore tag tree, summaries, bulk selection, current-novel tag sync, and built-in tag management (create/rename/delete/edit content) |
| `components/MidFormPanel.vue` | Middle directing workspace: manual Step1~Step4 flow; next step highlight after completion; hide non-current steps by default; auto-generate task draft for empty Step3 with one-click reset |
| `components/RightPanel.vue` | Run panel body (inserted into Drawer by `App.vue`), showing phases/token/main text/next-chapter hints/planning stream/graph entry |
| `components/dialogs/TextPreviewDialog.vue` | Generic long-text preview |
| `components/dialogs/CreateNovelDialog.vue` | Create novel dialog (supports auto-generated lore draft plus optional notes on creation) |
| `components/dialogs/InputPreviewDialog.vue` | Stage-by-stage input preview + structure-card display + risky-continue confirmation |
| `components/dialogs/NextChapterHintDialog.vue` | Legacy next-chapter dialog (main flow has moved to right-panel inline editing) |
| `components/dialogs/RoleManagerDialog.vue` | In-session role tags |
| `components/dialogs/ApiSettingsDialog.vue` | LLM provider config (DeepSeek / OpenAI-compatible); session cache + backend TTL model-list hit hints, force-refresh entry, capability tags, and connectivity test before save |
| `components/graph/GraphSliceCard.vue` | Lightweight middle-panel graph slice (node/edge counts, current event context, entry to full-screen studio) |
| `components/graph/GraphDialogs.vue` | Full-screen graph and side editor; `inject(GRAPH_INJECTION_KEY)` |
| `counter.ts` | Vite default counter demo; unused by `main.ts`, can be removed |
| `style.css` | Vite default global styles; current app mainly uses `theme-literary.css` + Element styles |
| `assets/*.svg` | Template assets not used by the main app |

---

## Technical Notes (File Level)

- `apiSse` event names and payloads must stay aligned with backend `run_stream`
  (including `done.consistency_audit`, `done.structure_gate`, `done.shadow_director`).
- `useGraph` must `dispose` charts and remove `resize` listeners on unmount.
- In TypeScript, narrow `unknown` from `apiJson` at call sites.
