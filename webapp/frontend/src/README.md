# `webapp/frontend/src` Directory Guide

After this refactor, this directory is layered as:
"shell components + composable orchestration + domain pure functions",
to prevent `App.vue` from growing further.

## Layering Conventions

- `App.vue`
  - Handles page assembly, component orchestration, theme switching,
    and minimal glue logic.
  - Avoid adding new pure computation/rule/reusable state machine logic here.
- `composables/`
  - Reusable state and behavior orchestration
    (run formatting, form models, tag-tree operations, etc.).
- `domain/`
  - Pure functions and domain rules (no UI, no network side effects).
- `components/`
  - Presentation and interaction, delegating outer logic via props/emits.
- `api/`
  - Network adapter layer (`apiJson` / `apiSse`).

## Refactor Outputs in This Round

- Extracted from `App.vue`:
  - `composables/useNovelRun.ts`
  - `composables/useNovelsAndForm.ts`
  - `composables/useLoreTags.ts`
  - `domain/tags.ts`

## Maintenance Suggestions

- For new logic, prefer `composables` / `domain` first to avoid flow-back into `App.vue`.
- Reuse `theme-literary.css` tokens for repeated component styles; avoid hard-coded colors.

## Event-Plan Flow (Frontend Convention)

- Workspace guides users in fixed order:
  `select existing event` -> `generate/regenerate event plan` -> `preview` -> `run`.
- `App.vue` performs lightweight pre-checks before `preview_input` / `run`
  (block directly in UI when no binding or no event plan).
- Final enforcement is backend-owned; frontend checks are usability hints, not authority.

