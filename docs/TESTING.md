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

## The `fake_module` Fixture (Mod Store / module_registry.py)

Testing `module_registry.py`'s discovery mechanism needs a real, importable `module_packages/<id>/`
package on disk — mocking `importlib` around it would just test the mock, and this codebase's own
"no mocks for the filesystem" rule (below) applies just as much to dynamic-import discovery as it
does to plain file reads. The `fake_module` fixture (in `conftest.py`) writes a real package into
the actual `app/backend/module_packages/` directory for the duration of one test, then deletes it
and purges it from `sys.modules` (Python caches imports — without this, one test's fake module
would leak into every later test that happens to reuse the same id).

```python
def test_something(fake_module, brain):
    fake_module("t_my_test_mod", MANIFEST_SRC, agent_tools_src=AGENT_TOOLS_SRC)
    # module_packages/t_my_test_mod/ now exists on disk with a real manifest.py
    ...
```

Always prefix test module ids with `t_` (or similar) — never reuse a real module id like
`"journal"`, since that will exist as a real package once modules start converting. Manifest source
is a plain Python string written to disk verbatim — see the existing test files
(`test_module_registry.py`, `test_dashboard_block_module_gating.py`, `test_agent_module_tools.py`)
for working manifest/router/dashboard_block/agent_tools templates to copy from. Most tests using
this fixture also need the `brain` fixture, since `mod_store_service.mark_installed()` and
`get_effective_disabled()`'s not-installed union both read/write Brain `_system/` files.

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

## Current Coverage (832 tests, 44 files)

Core-service coverage below (the module suites — finance, contacts, assets, help, etc. — make up the remainder of the files):

| File | Tests | What's covered |
|------|-------|----------------|
| `test_module_registry.py` | 8 | Discovery (valid module, malformed-module isolation, id-mismatch rejection, migration-name collision exclusion), `active_manifests()` install-state filtering, `register_routers()` failure isolation (optional logs-and-skips, locked crashes boot) |
| `test_mod_store_service.py` | 7 | Catalog merge (coming_soon→available, error status), install/uninstall round-trip, data-untouched-on-uninstall, history log survives reinstall |
| `test_features_service_modules.py` | 6 | `all_module_ids()` + `get_effective_disabled()`'s not-installed union |
| `test_brain_module_gating.py` | 5 | Bypass-confirmed-then-closed pairs: a module's `owned_brain_paths` hidden from the generic Brain browser only when disabled for that user (not instance-wide) |
| `test_dashboard_block_module_gating.py` | 5 | Catalog filtering + `render_block()`'s per-pass identity gating (viewer at pass 1, owner at pass 2's `share_underlying_data` exception) — including the subtle "viewer disabled, owner enabled" and "both disabled" cases |
| `test_agent_module_tools.py` | 5 | `_get_tools()` hard-excludes a disabled/not-installed module's tools; `_execute_tool()` actually dispatches through to a module's `agent_tools.py` |
| `test_help_service_modules.py` | 4 | `get_content()` merges a module's `help_section`; `capabilities_index()` annotates not-installed vs. disabled-but-installed vs. enabled |
| `test_features.py` | 15 | Role CRUD + name normalization (`features_service.py` + `routers/features.py`), `get_effective_disabled()` (role map, workspace-keyed dict, unknown-role fallback), assign-role-to-user round trip. Imports router functions directly, not just the service — see the file's own docstring for why |
| `test_file_service.py` | 25 | Atomic reads/writes, path resolution, `user_path`, `ws_path` |
| `test_notes_service.py` | 21 | Notes CRUD, folder management, move operations |
| `test_agent_notes_tools.py` | 8 | `agent_service.py`'s note tools only (not full agent orchestration — see Coverage Gaps): sharing-aware `list_notes`/`read_note`/`search_brain` visibility, `update_note`/`delete_note` access-level gating (contribute vs. edit), own-note CRUD unaffected |
| `test_profile_service.py` | 5 | Pool (`_household`/`_team`) priority order only — real-user profile behavior moved to `test_contacts.py` (self-contact) after the Profile/Contacts merge |
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
- `agent_service.py` — multi-tool agent orchestration itself (plan/auto/research mode logic, the actual LLM round-trip) is still untested (complex, requires mocked AI). Its note tools specifically are covered by `test_agent_notes_tools.py` as of 2026-08-14 (calls tool-handler code paths directly, no mocked AI needed since there's no LLM call in the resolve/access-check logic being tested) — same pattern would extend to the other tool families if this gap is revisited.
- `hosting_service.py` — reads `brain/hosting.json` at request time
- `n8n_service.py` — n8n REST API client (requires mocked httpx)
- `ha_service.py` — Home Assistant client (requires mocked httpx)
- `notification_service.py` — ntfy delivery
- `push_service.py` — VAPID subscription management
- `infisical_loader.py` — secret pull on startup
- `web_search_service.py` — Tavily search

`features_service.py` (`get_effective_disabled()` + role CRUD) was the previous highest-priority gap here — a bug there silently breaks module access for all users. Covered as of 2026-08-12 by `test_features.py`, prompted by a real bug found in the same area (see `docs/Daily Notes/2026-08-12.md`).

---

## Coverage Targets

These are the areas most critical to get right — test exhaustively here:

- `recurring_service._next_due` — date arithmetic including leap years, monthly/weekly/daily recurrence
- `priority_service.score_task` — scoring formula (category weight × priority weight + urgency bonus)
- `auth_service` — user CRUD, token issuance, JTI revocation, bcrypt
- `task_service` — CRUD, pagination, status transitions
- `file_service` — atomic write guarantees, path traversal rejection
