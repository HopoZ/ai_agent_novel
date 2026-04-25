---
name: ui-button-and-theme-sweep
description: Performs exhaustive frontend UI consistency sweeps for button semantics and dual-theme readability. Use when users report missed buttons, inconsistent styles, poor contrast, or theme pollution across Vue components.
---

# UI Button And Theme Sweep

Run a full-pass UI polish workflow focused on "no missed controls".

## When to Use

- User says some buttons are still not handled.
- User asks for full scan of similar UI issues.
- User reports white text unreadable or contrast problems.
- User asks to keep console theme and reading theme both clean.

## Do Not Use

- Backend-only tasks with no UI impact.
- Single known button fix when no global sweep is requested.

## Instructions

1. Discover all candidate controls:
   - Scan Vue files for `el-button`, `type="text"`, `type="link"`, and custom button classes.
   - Identify hardcoded color/background rules likely to leak across themes.
2. Normalize interaction semantics:
   - Primary action: `plain` + `primary`.
   - Destructive action: `plain` + `danger`.
   - Low-emphasis inline navigation: `link` only when contrast remains acceptable in both themes.
3. Enforce theme token usage:
   - Replace component hardcoded colors with shared CSS variables.
   - Keep console and literary values separated by theme-mode selectors.
4. Verify with a fixed checklist:
   - "open input/output", "preview/summary/detail", "view/delete", "studio/event-plan" style actions.
   - Dialog, panel, tag-tree, graph-related controls.
5. Run frontend verification:
   - Build/lint or the project's existing UI checks.
   - Report changed files and any remaining risky areas.

## Exit Criteria

- [ ] No known missed button variants remain.
- [ ] Both themes keep readable foreground/background contrast.
- [ ] No newly introduced hardcoded color in touched areas.
