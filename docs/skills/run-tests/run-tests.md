# Skill: run-tests

Run the LogCoreOS backend test suite and report results. Use this after any code change, before committing, or whenever correctness needs to be verified.

---

## Command

```bash
cd /path/to/LogCoreOS/app/backend
pytest tests/ -v --tb=short 2>&1
```

Replace `/path/to/LogCoreOS` with the actual repo root (e.g. `/home/user/LogCoreOS`).

---

## What to check in the output

**Parse for:**
- Lines containing `PASSED`, `FAILED`, `ERROR`, `WARNING`
- The summary line at the bottom: `X passed, Y failed, Z error in Ns`
- Any `ImportError` or `ModuleNotFoundError` — means a dependency is missing or an import path broke
- Any `fixture 'brain' not found` — means `conftest.py` is broken

**The `brain` fixture** (defined in `tests/conftest.py`) patches `settings.brain_path` to an isolated temp directory. Any test that touches the filesystem uses it. If it breaks, most tests will fail at setup — that's a conftest issue, not a logic issue.

---

## Coverage targets (per FOR_AI.md)

These modules must have test coverage. If any are missing, flag it:

| Module | Test file |
|--------|-----------|
| `services/recurring_service.py` — `_next_due()` | `tests/test_recurring_service.py` |
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
