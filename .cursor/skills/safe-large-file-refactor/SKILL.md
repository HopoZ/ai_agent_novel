---
name: safe-large-file-refactor
description: Refactors oversized mixed-responsibility files into clear layers without behavior drift. Use when a file becomes too large or messy and the user asks for architecture-based splitting.
---

# Safe Large File Refactor

Split "god files" into stable modules with low regression risk.

## When to Use

- User asks to split large files by architecture.
- A file mixes view state, domain rules, and orchestration.
- Feature delivery slowed by poor modularity.

## Do Not Use

- Tiny files with clear single responsibility.
- Urgent hotfixes where structural changes are unnecessary.

## Refactor Flow

1. Define seams before edits:
   - Keep route/component as shell.
   - Move pure rules to `domain`.
   - Move orchestration/state logic to `services` or `composables`.
2. Extract in small safe steps:
   - Move one concern at a time.
   - Preserve external API and payload shapes.
   - Keep naming consistent with existing codebase.
3. Protect compatibility:
   - Preserve monkeypatch/testing seams where existing tests depend on them.
   - Avoid hidden behavior changes during import rewiring.
4. Verify after each stage:
   - Run targeted tests for touched modules.
   - Run regression tests for the end-to-end flow.
5. Finish with readability:
   - Remove dead duplicated helpers from original large file.
   - Keep shell file focused on wiring and UI/API entrypoints.

## Exit Criteria

- [ ] Responsibilities are clearly separated by layer.
- [ ] Main flow behavior remains unchanged.
- [ ] Existing tests pass or are updated with justified changes.
