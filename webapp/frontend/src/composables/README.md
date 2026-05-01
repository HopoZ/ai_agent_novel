# `webapp/frontend/src/composables` Directory Guide

This directory contains reusable frontend state and behavior orchestration,
helping keep `App.vue` manageable.

## File Responsibilities

- `useGraph.ts`
  - Graph view state, filtering, search, edit actions, and API interaction.
- `usePanelResize.ts`
  - Left/middle panel drag widths and narrow-screen stacked layout behavior.
- `useNovelRun.ts` (new in this round)
  - Pure formatting logic for run results (audit summary, shadow director summary,
    and auto-retry display text).
- `useNovelsAndForm.ts` (new in this round)
  - Main form model and default parameter constants (`DEFAULT_LLM_*`).
- `useLoreTags.ts` (new in this round)
  - Tag tree selection, deselection, select-all, synchronization, and
    novel-scoped tag filtering.

## Boundary Rules

- Composables may depend on Vue reactivity APIs.
- Move pure rules to `../domain/` first, so composables do not become utility catch-alls.
- Avoid duplicating API assembly logic across composables; centralize via `api/client.ts`.

