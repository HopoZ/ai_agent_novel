# `webapp/backend/services` Directory Guide

This directory hosts backend orchestration services, extracting reusable logic from `routes`.

## File Responsibilities

- `auto_lore.py` (new in this round)
  - Auto-lore file template generation
  - Graph-guided rewrite entry points
  - Filename normalization and validation
  - Atomic writes and manifest read/write
- `novel_run.py` (new in this round)
  - Shared `run` flow logic: event binding validation, error code inference,
    EventPlan -> ChapterPlan conversion, and payload unwrapping

## Design Intent

- Reduce coupling in `routes/novels.py` between controller, business flow, and persistence details.
- Provide clear function boundaries that are easy to unit test.

## Maintenance Conventions

- Services may depend on `agents/*` and `persistence/*`, but should avoid FastAPI objects when possible.
- Public functions should keep explicit inputs/outputs and avoid reading global request context.

