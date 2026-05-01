# TOURMAP (Project Progress Map)

For module relationships and source-of-truth data flow, see [`ARCHITECTURE.md`](./ARCHITECTURE.md).
For per-directory details, see each directory's `README.md`.

## DONE

- [x] **Knowledge graph integrated into input compaction**
  - Added graph-aware context compaction before chapter generation.
  - Avoided injecting full cross-chapter history in manual timeline/event ownership scenarios.

- [x] **Frontend/backend flow switched to "preview first, run second"**
  - Main button now generates input preview first.
  - Streaming run starts only after explicit confirmation.
  - Added clearer phase labels (plan -> write -> save -> next-chapter hint).

- [x] **Graph visualization and editing upgraded**
  - Added full-screen graph view entry.
  - Added node/edge edits, relation removal, and timeline predecessor/successor updates.
  - Improved timeline markers for missing previous/next links.

- [x] **Storage evolved from single snapshot to table-oriented model**
  - Chapter/event/character data gradually split into structured storage.
  - Persistence now uses `storage/novels/<id>/novel.db` (`novel_state`, chapter rows, and four graph tables).
  - Pre-built chapter relation records before run, so event/chapter ownership lands before writing.

- [x] **Per-novel SQLite rollout**
  - Graph and chapter editing still uses existing `graph_tables` / `storage` APIs.
  - Underlying writes are handled by `novel_sqlite` into `novel.db`.

- [x] **Electron Windows installer (NSIS + PyInstaller backend)**
  - One-click script `build-windows-release.bat`.
  - Installer data lives in `data/` next to main exe.
  - Includes first-run in-app guidance for input/output folders.
  - See [electron/ELECTRON_RELEASE.md](../electron/ELECTRON_RELEASE.md).

- [x] **Streaming output and right-panel UX improvements**
  - Right-panel status text aligned with actual runtime flow.
  - Empty-state messages now reflect live run phases.
  - Added auto-scroll-to-bottom for right-panel output.

- [x] **Literary warm theme + continuation flow**
  - Added `theme-literary.css` paper-like palette and dialog/topbar styling.
  - Uses `Noto Serif SC` in `index.html`.
  - Next-chapter hint follows same input-preview chain as normal write flow.
  - Added optional "current map" injection path:
    `RunModeRequest.current_map` -> `build_llm_user_task`.

- [x] **Round close: flow/docs aligned (2026-04-25)**
  - [x] Next-chapter hint moved from modal to right-panel inline edit + one-click continue.
  - [x] Step1~4 changed from auto-jump to manual progression with next-step highlight.
  - [x] Step3 auto-drafts tasks when empty.
  - [x] Graph slice compressed into compact metric row + lightweight metadata.
  - [x] Outputs now stored by novel subdirectories.
  - [x] Tag management upgraded with built-in CRUD + bulk delete/prefix migration and sync.
  - [x] Planning flow now supports `ChapterPlan` wrapper unwrapping to reduce stream parse failures.

## TODO

### Current Assessment of "Novel Writing Mode" (2026-04)

- Conclusion: still missing the final "professional showrunner" feel.
  Current status is "generatable + editable + observable", but still too tool-like in
  structural constraints, auto-correction, and long-range payoff recovery.
- Main gaps:
  - Weak pre-write structure skeleton (authors still organize chapter goals/foreshadowing manually).
  - Post-write audit exists, but rule depth and closed-loop enforcement are still limited.
  - Graph visualization is strong, but bulk governance and quality auditing are not yet production-grade.

### P0 (Highest Priority, within 2 weeks)

- [x] **Consistency audit v2 (prompting -> constraints)**
  - [x] Added `block_reasons` and `recommended_actions` in `run_stream done`.
  - [x] Blocks auto "next chapter continue" on high-risk conflicts.
  - [x] Frontend now shows audit level, block reasons, and repair actions.
  - [x] Added high-risk rules: timeline reversal, character teleportation, unsupported relation jumps.

- [x] **Structure card (strong pre-write guidance)**
  - [x] Auto-fill and lock structure card in preview:
    goal / conflict / turning point / foreshadow recovery / event ownership.
  - [x] If minimum fields are missing, force either:
    "continue anyway (risky)" or "go back and complete".
  - [x] Backend strictly validates `structure_risk_ack`.

- [x] **Shadow director v2 (more invisible support)**
  - [x] Added recommendations for side characters, conflict type, and foreshadow recovery.
  - [x] Auto-applies detail strategy by default with one-click undo for last auto-direct.

### P1 (Secondary, 1-2 months)

- [x] **Frontend layout fast revamp (middle panel + graph)**
  - [x] Middle panel became a 4-step directing workspace.
  - [x] Graph now has dual mode: compact middle slice + full-screen studio.
  - [x] Run results moved into drawer-style panel.
  - [x] Kept low-operation, high-impact decisions:
    conflict type / foreshadow strategy / side-character intensity.
  - [x] Interaction refinements:
    hide non-current steps, top step status bar, next/prev buttons;
    then switched to manual progression + condition highlighting.

- [ ] **Graph governance (maintainability at large scale)**
  - Bulk edge editing by role/chapter/event type.
  - Quality audits: isolated nodes, dangling edges, self-loops,
    duplicate relations, broken timeline chains.
  - Import/export validation: schema checks, dry-run, row-level error locations.

- [ ] **Run observability upgrade**
  - Add `request_id`, phase timing, and error category code to each run.
  - Track failure distribution (network/model/parsing/persistence) for iteration.

- [x] **Model provider UX aligned with Chatbox**
  - Base support done: OpenAI-compatible provider, model list, pre-save connectivity test.
  - [x] Model list cache: backend TTL (`force_refresh`) + frontend session hit hints.
  - [x] Model capability labels shown in settings:
    `chat / vision / tool / reasoning`.

### P2 (Long-term productization)

- [ ] **Serialization skeleton and payoff system**
  - Mainline/branchline/foreshadow lifecycle management
    (plant -> advance -> recover -> validate).
  - Coverage/payoff dashboards to reduce unresolved plot threads.

- [ ] **Collaboration and safety**
  - Change audit logs for config/graph updates, snapshot rollback,
    and multi-user conflict handling.

### Next-session Preparation

- [ ] **Stability regression**
  - Run full chain on 3 novels:
    preview -> generate -> next chapter -> expand -> optimize.
  - Cover one `init_state` and one interrupted/resumed `write_chapter` stream.

- [ ] **Output and observability**
  - Explicitly show active output subdirectory (per novel) in right panel.
  - Add `request_id/phase/error_code` to key failures
    (start with `run_stream` done/error frames).

- [ ] **Graph governance step 1**
  - Add one-click checks/jump for isolated nodes and broken timelines.
  - Start with minimum viable bulk edge edits (delete by node type).

- [ ] **Docs and release**
  - Sync behavior changes to `ARCHITECTURE.md` and `RELEASE.md`
    with updated screenshots and example paths.
  - Output reusable "tomorrow validation checklist" to `outputs/`.

### Change List (Grouped by Feature)

#### 1) Consistency Audit v2
- Backend:
  - `agents/state/consistency_audit.py`
  - `webapp/backend/routes/novels.py`
  - `agents/novel/novel_agent.py` (if audit output participates in prompting)
- Frontend:
  - `webapp/frontend/src/App.vue`
  - `webapp/frontend/src/components/RightPanel.vue`
  - `webapp/frontend/src/components/MidFormPanel.vue`

#### 2) Structure Card (Pre-write Constraint)
- Backend:
  - `webapp/backend/schemas.py`
  - `webapp/backend/run_helpers.py`
  - `webapp/backend/routes/novels.py`
- Frontend:
  - `webapp/frontend/src/components/MidFormPanel.vue`
  - `webapp/frontend/src/components/dialogs/InputPreviewDialog.vue`
  - `webapp/frontend/src/App.vue`

#### 3) Graph Governance
- Backend:
  - `webapp/backend/routes/graph.py`
  - `agents/persistence/graph_tables.py`
  - `webapp/backend/graph_payload.py`
- Frontend:
  - `webapp/frontend/src/composables/useGraph.ts`
  - `webapp/frontend/src/components/graph/GraphDialogs.vue`

#### 4) Observability and Error Taxonomy
- Backend:
  - `webapp/backend/routes/novels.py`
  - `webapp/backend/sse.py`
  - `webapp/backend/app.py`
- Frontend:
  - `webapp/frontend/src/App.vue`
  - `webapp/frontend/src/components/RightPanel.vue`

#### 5) Ongoing Electron Installer Maintenance
- Docs and scripts:
  - `electron/ELECTRON_RELEASE.md`
  - `electron/README.md`
  - `packaging/pyinstaller/README.md`
  - `build-windows-release.bat`

## Engineering Risk Review Notes

1) **Critical data-consistency risk: no global transaction**

Current largest implementation weakness.

- Symptom: in `agents/persistence/graph_tables.py`, `persist_chapter_artifacts`
  calls `save_chapter`, `save_state`, `save_character_entities`, `save_event_rows`, etc.
  In `novel_sqlite.py`, each `save_*` method opens its own
  `with sqlite_connection(novel_id) as conn:`.
- Impact: no atomic transaction across the full write unit.
  If a crash happens after partial writes, SQLite may end in torn state (dirty data),
  and four graph tables can diverge from `NovelState`.
- Recommendation: adopt Unit of Work, or acquire one shared `conn` in
  `persist_chapter_artifacts`, pass it through all DB functions, and commit once at the outer layer.

2) **Hazardous context truncation: hard-cut JSON strings**

- Symptom (`agents/state/state_compactor.py`):

```python
s = json.dumps(payload, ensure_ascii=False, indent=2)
if len(s) > max_chars:
    return s[:max_chars] + "\n...[truncated]"
```

- Impact: this cuts valid JSON into invalid JSON, producing malformed `state_context`.
  LLMs are highly sensitive to structural syntax; malformed JSON can degrade attention
  and even contaminate output format behavior.
- Recommendation: never truncate after `json.dumps()`.
  Prune at dict level first (e.g., reduce `recent_summaries`, lower timeline item count),
  so serialized output remains valid JSON.

3) **Performance bottleneck: doing DB work in memory (O(N) scan)**

- Symptom: in `agents/persistence/graph_tables.py`, flows like
  `replace_chapter_belongs_for_chapter` load all relations into Python, filter with loops,
  then delete/reinsert whole lists.
- Impact: O(N) to O(N^2) behavior on larger novels; full-table read/write each chapter
  causes growing SQLite I/O and Python object overhead.
- Recommendation: push filtering and updates down to SQL.
  Example: expose methods like
  `DELETE FROM event_relations WHERE kind='chapter_belongs' AND source=?`.

4) **Fragile LLM output parsing: over-reliance on regex + retries**

- Symptom: logs show repeated hard failures after Pydantic "Field required" and retry attempts.
- Impact: custom extraction (`_extract_balanced_json_object`) and self-repair retries
  are brittle for deeply nested JSON (e.g., full `NovelState`), wasting tokens and hurting UX.
- Recommendation: adopt strict Structured Outputs (JSON Mode + JSON Schema) end-to-end
  with schema constraints at invocation time.

5) **SSE streaming lacks resume-from-breakpoint**

- Symptom: `write_chapter_text_stream` in `novel_agent.py` yields via `model.stream`.
- Impact: long chapter generation can fail mid-stream on network/rate limits;
  no checkpoint means users must restart and lose partial output/token spend.
- Recommendation: add continuation mechanism in frontend/backend.
  On stream interruption, assemble received chunks as prior assistant content,
  feed it back into context, and continue writing from the breakpoint.