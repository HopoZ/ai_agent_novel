# AI Novel Agent (This Release)

A Windows desktop writing assistant for long-form fiction authors.
It combines Lore context, task/chapter planning, streaming generation,
and graph workflows to keep world settings and serialization state aligned.

## Changes Since 1.0.0

### Added
- Graph now supports **right-drag edge creation** (character relation,
  timeline progression, appearance, chapter ownership).
- Story event graph supports **automatic horizontal ordering** by `timeline_next`
  (left to right).
- Event chapters can be **expanded by selected event**, with
  **expand/collapse all chapters** controls.

### Updated
- Batch edge deletion moved from the main panel to the secondary
  **Advanced Actions** drawer to free primary UI space.
- Removed the **Event Plan** button from the left panel to reduce duplicate entry points.

### Fixed
- Fixed encoding/parsing issues in `scripts/build-windows-release.ps1`
  under Windows PowerShell 5.1 (string/quote breakage).

## Upgrade Notes

- No forced data migration in this release; existing novel and graph data remains compatible.
- Drag-created graph edges are still validated by backend rules; invalid connections are rejected.

## Verification

- Frontend build passed: `webapp/frontend` -> `npm run build`.
- Regressed key paths: drag edge creation, event graph ordering,
  chapter expand toggles, and entry/panel layout changes.

## Known Notes

- Vite large chunk warnings (`>500kB`) may still appear during build.
  This is an existing warning and does not block release functionality.
