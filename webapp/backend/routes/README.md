# `webapp/backend/routes` Directory Guide

This is the FastAPI routing layer. After refactor, the target is "thin routes":
validate HTTP inputs, map errors, and delegate to service/domain modules.

## File Responsibilities

- `novels.py`
  - Core novel flow routes (create, run, SSE, event plans, etc.)
  - Lore-tag rules, auto-lore build logic, and part of shared run logic
    have been moved into `../domain` and `../services`
- `graph.py`
  - Graph APIs (node/edge CRUD and relation handling)
- `lore.py`
  - Tags, summaries, previews, and bulk tag management
- `settings.py`
  - Model configuration, connectivity checks, model lists
- `pages.py`
  - Page entry and fallback handling

## Routing Layer Conventions

- Keep complex business rules out of routes; call `services/*` first.
- Put domain rules under `../domain/*`.
- Keep response shape and error messages backward-compatible;
  prefer delegation over protocol changes.

## Event-Plan Flow Conventions

- In `novels.py`, write-related endpoints (`/run`, `/preview_input`, `/run_stream`) must:
  1) validate `existing_event_id` binding first;
  2) validate that the event has `event_plan`;
  3) allow write flow only after both checks pass.
- SSE error semantics and HTTP rejection messages must stay aligned
  (missing binding / missing plan).
- Routes must not silently auto-create plans, to avoid bypassing event-only constraints.

