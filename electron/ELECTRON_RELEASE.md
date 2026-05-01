# Electron Release Notes

This file records Electron desktop release-relevant behavior.

## Current Runtime Guarantees

- Desktop runs as a single instance per user session.
- Backend child process is cleaned up:
  - before spawning a new backend,
  - when app quits,
  - when debug relaunch is triggered.
- Portable runtime folders are auto-created under `<install-dir>/data`.

## Packaging Scope

- Installer target: Windows NSIS (`*-Setup.exe`).
- Backend executable is shipped from `resources/backend/` as external resource.
- Desktop logs remain local and portable in `<install-dir>/data/logs`.

## Regression Checklist

- Launch app twice quickly -> second launch should focus existing window.
- Close app -> verify no lingering `novel-backend.exe` in Task Manager.
- Reopen app -> no `Errno 10048` bind conflict on port `8000`.
- Trigger `File -> Debug Start` -> relaunch succeeds and backend still single-owned.
