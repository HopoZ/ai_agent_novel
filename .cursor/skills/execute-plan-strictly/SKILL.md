---
name: execute-plan-strictly
description: Executes attached implementation plans exactly under strict constraints. Use when the user asks to implement a plan as specified, forbids editing the plan file, requires sequential todo progress, or asks to finish all tasks without stopping.
---

# Execute Plan Strictly

Follow a strict execution contract for plan-driven work.

## When to Use

- User says "implement the plan as specified" or equivalent.
- User says "do not edit the plan file".
- User requires todo progression (`in_progress` -> `completed`) in order.
- User requires full completion in one continuous run.

## Do Not Use

- User only asks for brainstorming or high-level options.
- No explicit plan or task list exists.

## Instructions

1. Lock constraints first:
   - Treat the plan as read-only.
   - Do not rewrite scope without user approval.
   - Keep one active todo at a time.
2. Execute todos sequentially:
   - Mark first todo `in_progress`.
   - Implement code changes for that todo.
   - Run focused verification (tests/build/lint relevant to changed area).
   - Mark todo `completed` only after evidence.
3. Keep delivery persistent:
   - Continue until all todos are finished or a hard blocker appears.
   - If blocked, provide the exact blocker, attempted fixes, and the smallest decision needed from user.
4. Keep progress visible:
   - Send concise progress updates during longer runs.
   - Note current todo, what changed, and verification status.
5. Preserve user trust:
   - Never silently skip a todo.
   - Never claim verification without running checks.

## Completion Checklist

- [ ] Plan file untouched.
- [ ] Every todo moved through valid status transitions.
- [ ] Relevant checks executed and outcomes recorded.
- [ ] Final report includes completed scope and any residual risk.
