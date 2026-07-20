# LogCoreOS — Testing Guide

Tests live in `app/backend/tests/`. Run from `app/backend/`:

```bash
pytest tests/ -v                        # full suite
pytest tests/test_task_service.py -v    # single file
pytest tests/ -v -k "test_score"        # match by name pattern
```

---

## The `brain` Fixture

**Every test that reads or writes Brain files must use the `brain` fixture.**

```python
def test_something(brain):
    # brain is a tmp_path / "brain" directory
    # settings.brain_path is monkeypatched to point at it
    ...
```

What it does: patches `settings.brain_path` to a fresh temp directory and pre-creates `brain/_system/`. This isolates each test from the real filesystem and from other tests.

**Never use a real brain path in tests.** Tests that skip this fixture will read/write the developer's actual Brain files and will fail unpredictably in CI.

---

## How to Write a Test for a New Service

1. Import the service functions directly — don't go through routers.
2. Use the `brain` fixture for any test that needs the filesystem.
3. Use `monkeypatch` for anything that calls external services (AI provider, n8n, HA).
4. Test the function in isolation: one assert per test, clear arrange/act/assert structure.

Example skeleton:

```python
def test_create_thing_stores_file(brain):
    from services.my_service import create_thing, get_thing

    create_thing("Alice", title="Test")
    result = get_thing("Alice")

    assert result["title"] == "Test"
```

---

## Why No Mocks for the Filesystem

Tests use real filesystem operations via the `brain` fixture — **not** mock file objects. This is intentional: a mock file system that passes all tests but breaks on a real POSIX `os.replace()` call is worse than no test at all. Integration with the real filesystem is the guarantee that matters.

Exception: external HTTP calls (AI provider, n8n, HA, Tavily) should be mocked with `monkeypatch` or `unittest.mock.patch` to keep tests fast and offline.

---

## Current Coverage (474 tests, 27 files)

Core-service coverage below (the module suites — finance, contacts, assets, help, etc. — make up the remainder of the 27 files):

| File | Tests | What's covered |
|------|-------|----------------|
| `test_file_service.py` | 25 | Atomic reads/writes, path resolution, `user_path`, `ws_path` |
| `test_notes_service.py` | 21 | Notes CRUD, folder management, move operations |
| `test_profile_service.py` | 17 | Profile read/write, workspace-scoped paths, priority order |
| `test_events_service.py` | 16 | Calendar event CRUD |
| `test_priority_service.py` | 14 | Scoring formula, top3 logic, category weights, urgency bonus |
| `test_suggestions_service.py` | 19 | Suggestion types, custom schedule management, **channel-rotation reminder sweep (dedup + reset-on-rotation)** |
| `test_recurring_service.py` | 15 | Next-due arithmetic including leap years, streak logic |
| `test_task_service.py` | 15 | Task CRUD, pagination, type handling |
| `test_auth_service.py` | 22 | User CRUD, JWT create/verify, bcrypt, JTI revocation, constant-time login + account lockout, **notification-channel rotation** |
| `test_journal_service.py` | 13 | Daily entry CRUD |
| `test_rate_limiter.py` | 12 | IP-based rate limiting, window enforcement |

---

## Coverage Gaps (no tests yet)

The following services have no test file:

- `ai_provider.py` — AI abstraction layer (requires live API or mocked client)
- `agent_service.py` — multi-tool agent orchestration (complex, requires mocked AI)
- `hosting_service.py` — reads `brain/hosting.json` at request time
- `features_service.py` — `get_effective_disabled()` logic (workspace-keyed dict handling)
- `n8n_service.py` — n8n REST API client (requires mocked httpx)
- `ha_service.py` — Home Assistant client (requires mocked httpx)
- `notification_service.py` — ntfy delivery
- `push_service.py` — VAPID subscription management
- `infisical_loader.py` — secret pull on startup
- `web_search_service.py` — Tavily search

`features_service.get_effective_disabled()` is the highest-priority gap — it handles the workspace-keyed `disabled_modules` format + backward compat with flat lists, and a bug there silently breaks module access for all users.

---

## Coverage Targets

These are the areas most critical to get right — test exhaustively here:

- `recurring_service._next_due` — date arithmetic including leap years, monthly/weekly/daily recurrence
- `priority_service.score_task` — scoring formula (category weight × priority weight + urgency bonus)
- `auth_service` — user CRUD, token issuance, JTI revocation, bcrypt
- `task_service` — CRUD, pagination, status transitions
- `file_service` — atomic write guarantees, path traversal rejection
