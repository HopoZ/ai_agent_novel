## Security Fingerprint (Local Private)

Owner identity mark: `HopoZ Z7`  
Scope: source-code ownership fingerprint (not novel output watermark)

This document is local-only and should never be uploaded to public remotes.

## 1) Design goals

- Keep an ownership signal inside codebase with low visibility
- Ensure no runtime behavior change
- Make verification reproducible on local machine
- Allow periodic rotation without large refactor cost

## 2) Current implementation

### 2.1 Internal marker engine
- File: `agents/_internal_marks.py`
- Method: `z7_module_mark(code: str) -> str`
- Mechanism:
  - private seed + shard table
  - deterministic digest token generation
  - short token used as per-module revision marker

### 2.2 Embedded module markers
Current marker pattern:
- `_MODULE_REV = z7_module_mark("<code>")`

Current module code mapping:
- `na` -> `agents/novel/novel_agent.py`
- `lr` -> `agents/lore/lore_runtime.py`
- `sc` -> `agents/state/state_compactor.py`
- `sm` -> `agents/state/state_merge.py`
- `pb` -> `agents/prompt/prompt_builders.py`
- `tu` -> `agents/text_utils.py`
- `md` -> `agents/state/state_models.py`
- `lc` -> `agents/novel/llm_client.py`
- `lj` -> `agents/novel/llm_json.py`
- `tf` -> `agents/novel/timeline_focus.py`
- `si` -> `agents/novel/structured_invoke.py`

Notes:
- Marker variables are non-functional and side-effect free
- Markers are intentionally spread across core modules
- Names are kept close to internal revision style (not explicit watermark labels)

## 3) Verification method

### 3.1 Manual verification
Check each target module contains:
- import of `z7_module_mark`
- `_MODULE_REV = z7_module_mark("<code>")`

### 3.2 Scripted verification
Recommended local checker script (optional):
- `tasks/check_fingerprint.py`
- Command:
```bash
python tasks/check_fingerprint.py
```
- Expected:
  - `PASS` => all target files and markers are valid
  - `FAIL` => missing files or marker mismatch

## 4) Rotation policy

- Rotate seed/shard map at major milestones
- Keep old maps archived in private storage
- Avoid rotating too frequently (preserve continuity of evidence)
- After rotation, update checker rules accordingly

## 5) Safety and legal positioning

- This fingerprint is evidence assist, not sole legal proof
- Combine with:
  - commit history/tags/timestamps
  - `NOTICE` and `LICENSE`
  - release artifacts and logs

## 6) Operational rules

- Keep this file gitignored (already configured)
- Do not publish seed/table mapping in public docs
- Do not embed secrets/tokens in fingerprint constants
- If module path changes, update mapping and checker in same commit

