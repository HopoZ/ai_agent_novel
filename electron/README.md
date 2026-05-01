# `electron` — Desktop Runtime and Packaging

Electron main-process wrapper for the packaged backend (`novel-backend.exe`).
This module owns desktop lifecycle, backend child process lifecycle, and installer output.

## Runtime Behavior

- Single-instance lock is enabled. Second launch focuses the existing window.
- Backend cleanup runs before spawn to remove stale `novel-backend.exe`.
- On app quit/relaunch, Electron stops child backend and runs final cleanup.
- App auto-creates portable runtime directories:
  - `<install-dir>/data/logs`
  - `<install-dir>/data/lores`
  - `<install-dir>/data/outputs`
- Main and backend logs are written to:
  - `<install-dir>/data/logs/electron-main.log`

## Key Files

- `src/main/index.ts`: app lifecycle, backend spawn/cleanup, menu, debug handling.
- `src/preload/index.ts`: safe desktop API bridge for renderer usage.
- `electron.vite.config.ts`: Electron build config.
- `package.json`: desktop scripts and `electron-builder` packaging config.
- `resources/backend/`: bundled backend executable payload.

## Build Commands

From repository root:

```bash
cd electron
npm ci
npm run dist
```

`npm run dist` builds installer artifacts (NSIS target on Windows).
