---
name: refactor-doc-sync-and-regression
description: Synchronizes architecture documentation and regression verification after structural code changes. Use when refactors add or move modules, update dependency boundaries, or require release/document rollups.
---

# Refactor Doc Sync And Regression

Close the loop after refactor: docs aligned, tests verified, release notes updated.

## When to Use

- New layer/module directories are added.
- Responsibilities move across `routes/services/domain` or `App/composables/domain`.
- User asks to "补文档", "更新架构", or "回归验证".

## Do Not Use

- Trivial typo-only edits with no architecture impact.

## Instructions

1. Update nearest folder docs first:
   - Add or revise `README.md` in touched directories.
   - Document role, boundaries, and key files.
2. Update cross-project architecture docs:
   - Refresh architecture map and dependency direction.
   - Keep request-flow descriptions consistent with current code.
3. Update release/change log:
   - Record user-visible behavior changes and internal refactors.
4. Run verification stack:
   - Execute focused tests for changed modules.
   - Execute broader regression checks when workflow or routing changed.
5. Report with evidence:
   - List updated docs.
   - List executed checks and pass/fail results.
   - Note any residual gaps explicitly.

## Exit Criteria

- [ ] Folder docs and top-level architecture docs are consistent.
- [ ] Regression evidence exists for changed flows.
- [ ] Release notes include meaningful changes.
