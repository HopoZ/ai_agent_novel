# TOURMAP (Project Progress Map)

For architecture and source-of-truth boundaries, see [`ARCHITECTURE.md`](./ARCHITECTURE.md).
For directory-level details, see each module `README.md`.

## Project Snapshot

- **Current state**: core loop is stable (`preview -> run -> persist -> continue`), but still short of a full "professional showrunner" experience.
- **Strengths**: generation quality, observability, graph editing, and end-to-end workflow are in place.
- **Main gaps**: stronger graph governance, better run observability, and long-range plot payoff tooling.

---

## Completed Milestones

### Core Flow

- [x] Graph-aware input compaction before chapter generation.
- [x] "Preview first, run second" interaction model.
- [x] Streaming phase clarity (`plan -> write -> save -> next hint`).
- [x] Per-novel SQLite rollout using `storage/novels/<id>/novel.db`.

### UX and Product

- [x] Full-screen graph + richer node/edge editing.
- [x] Right-panel streaming UX improvements and auto-scroll.
- [x] Warm literary theme and continuation flow refinements.
- [x] Mid-panel step workspace moved to manual progression.
- [x] Tag management supports CRUD + bulk operations.
- [x] Planning stream handles `ChapterPlan` wrappers robustly.

### Release and Packaging

- [x] Electron Windows installer flow (`build-windows-release.bat`).
- [x] PyInstaller backend packaging integrated into desktop build.

---

## Active Backlog

## P1 (Current Focus, 1-2 months)

- [ ] **Graph governance**
  - Bulk edge editing by role/chapter/event type.
  - Quality checks: isolated nodes, dangling edges, self loops, duplicates, broken timelines.
  - Import/export validation with schema + dry-run + row-level error location.

- [ ] **Run observability**
  - Add `request_id`, phase duration, and error category to each run.
  - Track failure distribution (network/model/parsing/persistence).

## P2 (Long-term Productization)

- [ ] **Serialization skeleton and payoff system**
  - Mainline/branchline/foreshadow lifecycle (`plant -> advance -> recover -> validate`).
  - Coverage and payoff dashboards.

- [ ] **Collaboration and safety**
  - Audit logs for settings/graph changes, snapshot rollback, and multi-user conflict handling.

---

## Next Session Plan (Practical Checklist)

- [ ] **Stability regression**
  - Run full chain on 3 novels:
    `preview -> generate -> next chapter -> expand -> optimize`.
  - Include one interrupted/resumed `write_chapter` stream.

- [ ] **Output and observability**
  - Show active output subdirectory (per novel) in right panel.
  - Add `request_id/phase/error_code` to key failure surfaces.

- [ ] **Graph governance step 1**
  - Add one-click checks/jump for isolated nodes and broken timelines.
  - Deliver minimum viable bulk edge editing (delete by node type).

- [ ] **Docs and release sync**
  - Align behavior changes in `ARCHITECTURE.md` and `RELEASE.md`.
  - Generate a reusable "tomorrow validation checklist" under `outputs/`.

---

## File Touch Map (By Feature)

### Consistency Audit v2

- Backend:
  - `agents/state/consistency_audit.py`
  - `webapp/backend/routes/novels.py`
  - `agents/novel/novel_agent.py`
- Frontend:
  - `webapp/frontend/src/App.vue`
  - `webapp/frontend/src/components/RightPanel.vue`
  - `webapp/frontend/src/components/MidFormPanel.vue`

### Structure Card (Pre-write Constraint)

- Backend:
  - `webapp/backend/schemas.py`
  - `webapp/backend/run_helpers.py`
  - `webapp/backend/routes/novels.py`
- Frontend:
  - `webapp/frontend/src/components/MidFormPanel.vue`
  - `webapp/frontend/src/components/dialogs/InputPreviewDialog.vue`
  - `webapp/frontend/src/App.vue`

### Graph Governance

- Backend:
  - `webapp/backend/routes/graph.py`
  - `agents/persistence/graph_tables.py`
  - `webapp/backend/graph_payload.py`
- Frontend:
  - `webapp/frontend/src/composables/useGraph.ts`
  - `webapp/frontend/src/components/graph/GraphDialogs.vue`

### Observability and Error Taxonomy

- Backend:
  - `webapp/backend/routes/novels.py`
  - `webapp/backend/sse.py`
  - `webapp/backend/app.py`
- Frontend:
  - `webapp/frontend/src/App.vue`
  - `webapp/frontend/src/components/RightPanel.vue`

### Electron Packaging Maintenance

- Docs/scripts:
  - `electron/ELECTRON_RELEASE.md`
  - `electron/README.md`
  - `packaging/pyinstaller/README.md`
  - `build-windows-release.bat`

---

## Engineering Risk Backlog

### R1. Missing end-to-end transaction in chapter persistence (High)

- **Symptom**: `persist_chapter_artifacts` writes chapter/state/entities in separate DB connections.
- **Impact**: partial crash can leave torn data between graph tables and `NovelState`.
- **Action**: move to Unit of Work or shared connection + single outer commit.

### R2. Invalid JSON risk from hard truncation (High)

- **Symptom**: state context can be cut after `json.dumps`, producing malformed JSON.
- **Impact**: degraded LLM reasoning/output reliability.
- **Action**: prune structured payload before serialization; never truncate serialized JSON.

### R3. In-memory graph relation rewrites at scale (Medium)

- **Symptom**: load/filter/rewrite full relation lists in Python.
- **Impact**: O(N) to O(N^2) behavior as novels grow.
- **Action**: push filtering/deletion/update logic into SQL with targeted `WHERE` operations.

### R4. Fragile LLM parsing with regex/retry loops (Medium)

- **Symptom**: repeated hard failures after schema mismatch retries.
- **Impact**: token waste and unstable UX.
- **Action**: enforce structured outputs (JSON mode + schema constraints) end-to-end.

### R5. No stream resume on interruption (Medium)

- **Symptom**: interrupted SSE run loses partial generation.
- **Impact**: users must restart long writes and lose tokens/time.
- **Action**: add chunk checkpoint and continue-from-prefix flow.