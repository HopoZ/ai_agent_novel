# PyInstaller Backend Packaging (Windows)

Goal: build **`novel-backend.exe`**, copy it to **`electron/resources/backend/`**,
then run `cd electron && npm run dist`. The generated Electron installer can start
this backend exe on machines without Python installed.

For end-to-end release steps (including one-click scripts), see
**[`electron/ELECTRON_RELEASE.md`](../../electron/ELECTRON_RELEASE.md)**.

## 1. Environment

- The same Python 3.11+ virtual environment used by this project
- `pip install -r requirements.txt`
- `pip install pyinstaller`

## 2. Entry Script

Use `run_uvicorn.py` to start uvicorn from the repository root.

## 3. Recommended Command (add hidden imports as needed)

Run from the **repository root**:

```bash
pyinstaller --noconfirm --clean --onefile --name novel-backend ^
  packaging/pyinstaller/run_uvicorn.py ^
  --paths . ^
  --add-data "webapp/frontend/dist;webapp/frontend/dist" ^
  --add-data "webapp/static;webapp/static" ^
  --add-data "webapp/templates;webapp/templates" ^
  --collect-all uvicorn ^
  --collect-all fastapi ^
  --collect-all starlette ^
  --collect-all pydantic ^
  --collect-submodules agents ^
  --collect-submodules webapp
```

You **must** include **`--collect-submodules webapp`**.
`uvicorn` lazy-loads `webapp.backend.server` from a string, which static analysis
cannot detect. Without it, the exe fails at startup with:
`ModuleNotFoundError: No module named 'webapp.backend'` (process exits with code 1).

If you encounter **`RuntimeError: Directory 'webapp/static' does not exist`**:
when `webapp/static` is empty, `--add-data` may not include it. The app startup
already creates it in **`webapp/backend/app.py`**, and you can keep placeholders
like `README.txt` in `webapp/static` and `webapp/templates` to ensure inclusion.

If LangChain, agents, or other submodules are missing, add `--hidden-import=...`
or additional `--collect-submodules ...` entries.

After success, copy `dist/novel-backend.exe` to
**`electron/resources/backend/novel-backend.exe`**.

## 4. Runtime Notes

In frozen mode, **`run_uvicorn.py`** sets `os.chdir(sys._MEIPASS)`. Without this,
Electron starts the backend with `cwd=resources/backend`, relative paths like
`webapp/static` are not found, and the process exits immediately.

Electron sets:

- `NOVEL_AGENT_STORAGE_DIR` -> in installer builds:
  **`<main exe directory>/data`** (`lores/`, `outputs/`, `novels/`, etc.)
- `NOVEL_AGENT_OUTPUTS_DIR` defaults to `STORAGE_DIR/outputs` if not explicitly set
- `SKIP_FRONTEND_BUILD=1`
- `NOVEL_AGENT_PORT` can match the main process port (default `8000`)

## 5. Notes

- Single-file exe size can be large; slower cold starts are expected.
- If PyInstaller conflicts with dependencies, switch to **onedir mode** (`--onedir`)
  and point Electron to the generated `novel-backend.exe` path.

## 6. CI/CD Release Notes

For GitHub Actions deployment (`.github/workflows/build-exe.yml`):

- Release tags should use `v*` (example: `v2.1.0`).
- CI copies `dist/novel-backend.exe` to `electron/resources/backend/novel-backend.exe`,
  then runs `electron npm run dist`.
- GitHub Release assets are expected from `electron/release/`:
  - `*.exe`
  - `*.blockmap`
  - `latest*.yml`
