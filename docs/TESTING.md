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

**Since 2026-08-25, `brain` also marks every LOCKED (`uninstallable: True`) module installed** (currently just `tasks`) — this matches real production behavior exactly: `main.py`'s `lifespan()` always runs pending migrations (which mark a locked module installed unconditionally, no existence-guard) before the app ever serves a single request, so no real running instance can ever reach a state where a locked module isn't installed. A test that needs to exercise that module's own *fresh-install* migration logic in isolation should call `mod_store_service.mark_uninstalled(module_id, by=...)` first to undo the fixture's own auto-install, then re-run the migration or call `mod_store_service.mark_installed()` — see `test_tasks_module_conversion.py` for the pattern. Optional modules (journal, home_assistant, automations, calendar, household, team) are unaffected — they still start NOT installed by default, same as before; a test that needs one still calls `mod_store_service.mark_installed()` explicitly (see e.g. `test_agent_approve_mode.py::test_new_tools_are_write_gated_by_default`, which needs household installed for `add_shared_task`'s schema to appear at all).

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

## Current Coverage (950 tests, 57 files + module_packages/{journal,automations,household,team,chat,notes,dashboard}/tests/)

Core-service coverage below (the module suites — finance, contacts, assets, help, etc. — make up the remainder of the files). Since 2026-08-24, `testpaths` (pyproject.toml) covers both `tests/` and `module_packages/` — run bare `pytest`/`pytest -v` for the full suite, or `pytest tests/ -v` to narrow to core-only (an explicit path on the command line overrides `testpaths`).

| File | Tests | What's covered |
|------|-------|----------------|
| `module_packages/journal/tests/test_journal_service.py` | 18 | Journal's own CRUD logic — moved verbatim from `tests/test_journal_service.py` when journal converted into a module (2026-08-24), import path updated only |
| `test_journal_module_conversion.py` | 6 | The conversion machinery, not journal's CRUD: `m015` fresh-vs-upgrade migration split, `on_install`/`on_new_user` backfill hooks (incl. pseudo-user exclusion), a full install→uninstall→reinstall round-trip proving data survives the whole cycle |
| `module_packages/automations/tests/test_inbox_service.py` | 15 | The Automation Inbox's own routing/dedup/review-gating/notification logic — moved verbatim from `tests/test_automation_inbox.py` when automations converted into a module (2026-08-25); import paths updated to the moved router/service, nothing else changed |
| `test_automations_module_conversion.py` | 3 | The conversion machinery, not the Inbox's own logic: `m019` fresh-vs-upgrade migration split (same features.json-existence idiom as journal's m015 — automations was always-on, unlike Home Assistant's opt-in ha_config.json guard), a full install→uninstall→reinstall round-trip proving data survives the whole cycle. Smaller than journal's/Home Assistant's own conversion suites since automations has no on_install/on_new_user hooks (nothing needs backfilling) and no id/brain-folder/block-type rename this time — id and every internal name were deliberately left alone, only the display name ("n8n Automation") changed |
| `test_calendar_module_conversion.py` | 4 | The conversion machinery, not events_service's own CRUD logic (untested even before this conversion — it stays in core, shared with Household/Team, and remains an existing coverage gap): `m020` fresh-vs-upgrade migration split (same features.json-existence idiom as journal's m015/automations' m019 — calendar was always-on, unlike Home Assistant's opt-in ha_config.json guard), a full install→uninstall→reinstall round-trip, and — the real guarantee behind this conversion being safe to ship — Household's own pool calendar (`_household` pseudo-user) staying reachable regardless of the personal Calendar module's install state, confirmed at the service layer since the actual gating is `require_module("household")`, a router-level `Depends()` already covered by Household's own tests |
| `test_tasks_module_conversion.py` | 4 | The conversion machinery for the first LOCKED (`uninstallable: True`) module — not task_service's own CRUD logic (already covered by `test_task_service.py`, unaffected since it stays in core): `m021`'s migration function marks tasks installed with NO existence-guard at all (unlike every optional module's guarded upgrade migration, since tasks was never optional — verified both by calling the migration function directly after undoing the `brain` fixture's own auto-install, and via `run_pending()` against a brain with no `_system/features.json` at all); a real-discovery-path proof (not just `test_module_registry.py`'s synthetic fake module) that a broken `get_router()` on the actual shipped tasks manifest crashes boot via `LockedModuleRegistrationError`; and a real 400 through the actual `POST /mod-store/uninstall/tasks` router function, confirming a locked module can't be uninstalled at the API layer, not just hidden in the UI |
| `test_household_module_conversion.py` | 6 | `m022`'s guarded (features.json-existence) upgrade migration, same idiom as journal's/automations'/calendar's — household, unlike tasks, is optional, so it needs the guard; install→uninstall→reinstall round-trip; `m023`'s pool_tasks block-type SPLIT (not a flat 1:1 rename like home_assistant's m018) — a dashboard's own workspace decides whether its `pool_tasks` block becomes `household_tasks` or `team_tasks`, verified for both directions in one migration run, plus that an unrelated block type is left untouched and the migration is idempotent on a second run |
| `test_team_module_conversion.py` | 3 | `m024`'s guarded upgrade migration + install→uninstall→reinstall round-trip — mirrors household's own shape; team declares no block-type-rename migration of its own, since household's m023 handles both halves of the pool_tasks split in one pass (see that file's own tests) |
| `module_packages/household/tests/test_household_router.py` | 11 | First-ever coverage of `module_packages/household/backend/router.py`'s own CRUD logic (task_service/events_service themselves are already covered elsewhere) — created_by/completed_by attribution, 404 on a missing task/event, 400 on a malformed UUID, and the real guarantee AGENTS.md documents: a household write is provably invisible to a `_team`-scoped `task_service.list_tasks()` query. Endpoint functions are called directly with a pre-resolved user dict (this suite's established convention, see test_mod_store_router.py) — the `require_module`/`require_pool_edit` dependency chain itself is untested here, a pre-existing gap across this whole test suite's routers this conversion isn't scoped to close |
| `module_packages/team/tests/test_team_router.py` | 11 | Mirrors household's own router test file exactly, same reasoning, `_team` pool instead |
| `test_chat_module_conversion.py` | 5 | The conversion machinery for the second LOCKED (`uninstallable: True`) module, after tasks — not `agent_service.py`'s own orchestration logic (still untested, see Coverage Gaps; confirmed unchanged by this conversion, it stays core infrastructure): `m025`'s migration function marks chat installed with NO existence-guard (same shape as tasks' m021, since chat was never optional); a real-discovery-path proof that a broken `get_router()` on the actual shipped chat manifest crashes boot via `LockedModuleRegistrationError`; a real 400 through `POST /mod-store/uninstall/chat`; and the real gap this conversion closed — `owned_brain_paths=["Chats"]` actually excludes the Chats folder from `brain_paths_for_disabled()`'s conditional union only when chat is disabled for that user, not when it's enabled |
| `module_packages/chat/tests/test_chat_router.py` | 14 | Moved from `tests/test_chat_sessions.py` when chat converted (2026-08-26) — `_write_chat_archive` markdown formatting, `POST /chat`'s session-creation/reuse/error-recovery paths, `GET /chat/pending/{chat_id}`'s live-card and question-derivation logic, resume-history alternation edge cases, and presence-gated notification skip/send — importing from `module_packages.chat.backend.router` instead of `routers.chat` |
| `test_chat_sessions.py` | 10 | Trimmed to pure `agent_service.py` coverage after chat's router-dependent tests moved out (2026-08-26, see above) — session-index helpers (list/rename/delete, ordering) and presence bookkeeping only; the router-facing tests and their `alice` fixture left with the moved file since they exercised `POST /chat`/`GET /chat/pending` directly, not `agent_service` in isolation |
| `module_packages/household/tests/test_agent_tools.py` | 16 | Moved from `tests/test_agent_member_resolution.py` when household converted (2026-08-25) — `_resolve_member_name`'s fuzzy name matching + the tool executor integration (`add_shared_task`/`update_shared_task`/`list_household_members`), now importing `_resolve_member_name` from `module_packages.household.backend.agent_tools` instead of `services.agent_service`; the `members` fixture now explicitly marks household installed, since (unlike tasks) it isn't locked and the `brain` fixture no longer auto-installs it |
| `test_home_agent_tools.py` | 6 | Home's double gate on its 4 AI tools — installed AND Home Assistant actually configured, either alone isn't enough; `get_home_assistant_state`'s real, deliberate asymmetry (read-only/no-approval-needed but excluded from research mode specifically, preserved as a hardcoded name in `agent_service.py` rather than the generic `read_only_agent_tools` union, which would've added it to both sets); a real dispatch call through to `ha_service` |
| `test_home_module_conversion.py` | 22 | `m016`'s migration guard (keyed on `ha_config.json`'s real content, not just existence); `m017`'s id-rename carry-forward (installed_modules.json key, features.json per-role key, auth.json per-user disabled_modules in both shapes, the real Brain folder rename); `m018`'s block-type-rename carry-forward (a real per-user dashboard, a pool dashboard, a per-user template, the global template, an unrelated block type left untouched) — all with a run-twice idempotency check each; install→uninstall→reinstall preserving favourites |
| `test_module_registry.py` | 8 | Discovery (valid module, malformed-module isolation, id-mismatch rejection, migration-name collision exclusion), `active_manifests()` install-state filtering, `register_routers()` failure isolation (optional logs-and-skips, locked crashes boot) |
| `test_mod_store_service.py` | 7 | Catalog merge (coming_soon→available, error status), install/uninstall round-trip, data-untouched-on-uninstall, history log survives reinstall |
| `test_mod_store_router.py` | 9 | The router's own endpoint functions (`install`/`uninstall`/`restart`), not just the service layer — 404/409 validation, the online-users 409 conflict + `force` bypass, and `restart()`'s self-restart-must-be-deferred regression test (a fake `docker` module injected via `monkeypatch.setitem(sys.modules, "docker", ...)`, since the SDK is imported locally inside the function; asserts `container.restart()` is **not** called until the `BackgroundTasks` job actually runs, and that a Docker connection failure still 502s synchronously) |
| `test_features_service_modules.py` | 6 | `all_module_ids()` + `get_effective_disabled()`'s not-installed union |
| `test_brain_module_gating.py` | 5 | Bypass-confirmed-then-closed pairs: a module's `owned_brain_paths` hidden from the generic Brain browser only when disabled for that user (not instance-wide) |
| `test_dashboard_block_module_gating.py` | 5 | Catalog filtering + `render_block()`'s per-pass identity gating (viewer at pass 1, owner at pass 2's `share_underlying_data` exception) — including the subtle "viewer disabled, owner enabled" and "both disabled" cases |
| `test_agent_module_tools.py` | 5 | `_get_tools()` hard-excludes a disabled/not-installed module's tools; `_execute_tool()` actually dispatches through to a module's `agent_tools.py` |
| `test_help_service_modules.py` | 4 | `get_content()` merges a module's `help_section`; `capabilities_index()` annotates not-installed vs. disabled-but-installed vs. enabled |
| `test_features.py` | 15 | Role CRUD + name normalization (`features_service.py` + `routers/features.py`), `get_effective_disabled()` (role map, workspace-keyed dict, unknown-role fallback), assign-role-to-user round trip. Imports router functions directly, not just the service — see the file's own docstring for why |
| `test_file_service.py` | 25 | Atomic reads/writes, path resolution, `user_path`, `ws_path` |
| `test_notes_service.py` | 29 | Notes CRUD, folder management, move operations, archiving |
| `test_notes_sharing.py` | 6 | Sharing specifically: handshake + folder cascade, contribute/edit access levels, `hidden_from` beats an accepted share, pool contributors, `list_visible_notes` includes shared, path-traversal rejection |
| `test_agent_notes_tools.py` | 3 | Trimmed to `search_brain`'s note-sharing awareness only (2026-08-26, once notes/ converted) — the one note-adjacent AI tool that stays core, since it also rglobs journal/memory/profile files. The other 6 note tools moved to `module_packages/notes/tests/test_notes_agent_tools.py`. Includes the same-day follow-up gap: `search_brain`'s shared/pool-notes half bypassed `_brain_skip()` entirely, unlike its own-files half — a disabled viewer could still search content shared with them |
| `module_packages/notes/tests/test_notes_agent_tools.py` | 6 | The 6 CRUD/folder tools that moved into `module_packages/notes/backend/agent_tools.py` — sharing-aware `list_notes`/`read_note` visibility, `update_note`/`delete_note` access-level gating (contribute vs. edit), own-note CRUD unaffected. Calls `agent_service._execute_tool()`, still core; routes here via the module-dispatch fallback |
| `module_packages/notes/tests/test_notes_router.py` | 13 | First-ever HTTP-layer coverage of `module_packages/notes/backend/router.py` (`notes_service.py`'s own CRUD/sharing logic is covered above) — CRUD, 404/409 handling, pool-note admin gating, archive/unarchive, and the sharing handshake end to end (share → pending → respond → visible; leave; leaving your own note rejected) |
| `test_notes_module_conversion.py` | 6 | The conversion machinery for notes/ — not notes_service's own CRUD/sharing logic (covered above): `m026`'s guarded (features.json-existence) upgrade migration, install→uninstall→reinstall round-trip, and the three real, pre-existing enforcement gaps this conversion closes: unfiltered AI tools (`_get_tools()`), no `owned_brain_paths` entry, and `note_embed`'s ungated dashboard block |
| `test_dashboards_service.py` | 41 | Dashboard CRUD/access, template sync/detach, sharing, `stacked_layout()`'s bottom-stack math, cross-workspace visibility — stays core, `dashboards_service.py` never moved when dashboard/ converted (2026-08-27) |
| `module_packages/dashboard/tests/test_dashboard_agent_tools.py` | 19 | Moved in full from `tests/test_agent_dashboard_tools.py` when dashboard/ converted — all 10 dashboard tools moved (unlike notes', no core-staying exception tool exists here). Access-tier gating, templated-dashboard block-mutation rejection, the global-template admin gate, the block catalog's merged `config_fields`, and the `y: Infinity`→`null` bug class staying fixed server-side |
| `module_packages/dashboard/tests/test_dashboard_router.py` | 8 | First-ever HTTP-layer coverage of this router (`dashboards_service.py`'s own logic is covered above) — CRUD, 404, floor-of-one delete protection (409), pool-create admin gating, and the real discovery that pool dashboards default to admin-only access (no implicit workspace-wide read the way pool Notes/Tasks get — a genuine design difference, confirmed by reading `_contributor_access()`, not a bug) |
| `test_dashboard_module_conversion.py` | 6 | The conversion machinery for the third LOCKED module (`uninstallable: True`) after Tasks and Chat — not `dashboards_service.py`'s own logic (covered above): `m027`'s unconditional (no existence-guard) upgrade migration, a real discovery-path boot-crash proof, a real 400 through `POST /mod-store/uninstall/dashboard`, and the two real, pre-existing enforcement gaps this conversion closes: unfiltered AI tools, and confirming `"Dashboards"` sits in the unconditional structural skip set (like Tasks) rather than the conditional per-user one (like Notes/Chats) |
| `test_profile_service.py` | 5 | Pool (`_household`/`_team`) priority order only — real-user profile behavior moved to `test_contacts.py` (self-contact) after the Profile/Contacts merge |
| `test_events_service.py` | 16 | Calendar event CRUD |
| `test_priority_service.py` | 14 | Scoring formula, top3 logic, category weights, urgency bonus |
| `test_suggestions_service.py` | 19 | Suggestion types, custom schedule management, **channel-rotation reminder sweep (dedup + reset-on-rotation)** |
| `test_recurring_service.py` | 15 | Next-due arithmetic including leap years, streak logic |
| `test_task_service.py` | 15 | Task CRUD, pagination, type handling |
| `test_auth_service.py` | 22 | User CRUD, JWT create/verify, bcrypt, JTI revocation, constant-time login + account lockout, **notification-channel rotation** |
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
