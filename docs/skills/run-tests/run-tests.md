# Skill: run-tests

Run the LogCoreOS backend test suite and report results. Use this after any code change, before committing, or whenever correctness needs to be verified.

---

## Command

```bash
cd /path/to/LogCoreOS/app/backend
pytest -v --tb=short 2>&1
```

Replace `/path/to/LogCoreOS` with the actual repo root (e.g. `/home/user/LogCoreOS`).

**Bare `pytest` is required for the real full suite** — since 2026-08-24, a converted module's own tests live in `module_packages/<id>/tests/`, not just `tests/`. `pyproject.toml`'s `testpaths = ["tests", "module_packages"]` only applies when no path is given on the command line, so `pytest tests/ -v` silently narrows to core-only and misses every module's own tests (hundreds of them) — see `docs/TESTING.md`.

---

## What to check in the output

**Parse for:**
- Lines containing `PASSED`, `FAILED`, `ERROR`, `WARNING`
- The summary line at the bottom: `X passed, Y failed, Z error in Ns`
- Any `ImportError` or `ModuleNotFoundError` — means a dependency is missing or an import path broke
- Any `fixture 'brain' not found` — means `conftest.py` is broken

**The `brain` fixture** (defined in `tests/conftest.py`) patches `settings.brain_path` to an isolated temp directory. Any test that touches the filesystem uses it. If it breaks, most tests will fail at setup — that's a conftest issue, not a logic issue.

---

## Coverage targets

See `docs/TESTING.md` for the full, current coverage guide (the `brain` fixture pattern, how to write a test for a new service, and per-module coverage expectations) — a hardcoded list here would drift the same way this section already had (it previously pointed at a nonexistent `docs/FOR_AI.md`). At minimum, confirm these core files still have real coverage:

| Module | Test file |
|--------|-----------|
| `services/recurrence_engine.py` — recurring-task date math | `tests/test_recurrence_engine.py` |
| `services/priority_service.py` — `score_task()` | `tests/test_priority_service.py` |
| `services/auth_service.py` — user CRUD, tokens, revocation | `tests/test_auth_service.py` |
| `services/task_service.py` — CRUD, pagination | `tests/test_task_service.py` |

---

## How to report

After running, report in this format:

```
TEST RESULTS
------------
Total:   X
Passed:  X
Failed:  X
Errors:  X
Status:  GREEN | RED

Failures:
- test_name (tests/file.py::TestClass::test_name)
  Error: <one-line summary>
```

If all pass: status is GREEN. If any fail or error: status is RED. List every failure with enough context to locate and fix it.

---

## If tests fail

1. Read the full traceback for each failure
2. Identify whether it is a logic error, a missing fixture, or a broken import
3. Fix the root cause — do not skip or comment out failing tests
4. Re-run to confirm GREEN before reporting done
