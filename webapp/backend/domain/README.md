# `webapp/backend/domain` Directory Guide

This directory holds backend domain rules (rule-first, framework-light).

## File Responsibilities

- `novel_lore_tags.py` (new in this round)
  - Lore tag normalization
  - Novel-scoped filtering for auto-generated tags
  - Merge and dedupe rules (keep current novel auto tags, drop auto tags from other novels)

## Conventions

- Keep domain logic as independently testable pure functions whenever possible.
- Do not handle HTTP protocol details and do not depend directly on FastAPI.

