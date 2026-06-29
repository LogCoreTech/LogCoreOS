# Skill: diagnose

Run a full diagnostic audit of the LogCoreOS codebase. Covers security, architecture, strategy, and code logic. Use this after a batch of changes, before a release, or whenever the codebase needs a health check.

Read `docs/FOR_AI.md` before running this audit — it defines the project's principles, conventions, and known limitations that all findings should be measured against.

---

## 1. Security

Check for:

- **Auth gaps** — any router endpoint missing `Depends(get_current_user)` or `Depends(require_module(...))` that should have one
- **Input validation** — user-controlled strings written to files or injected into AI prompts without sanitization
- **Cookie security** — `httponly=True`, `samesite="strict"`, `secure=settings.cookie_secure` on auth cookie
- **Path traversal** — any path built from user input that doesn't go through `user_path()` or pass `.relative_to()` containment check
- **Rate limiting** — endpoints with no `rate_limit()` dependency, especially: unauthenticated endpoints, write operations, AI-calling endpoints, CPU-intensive operations (zip, etc.)
- **CORS** — wildcard `allowed_origins="*"` with `allow_credentials=True` is invalid per CORS spec; verify the wildcard case uses `allow_origin_regex`
- **Prompt injection** — brain content injected into AI system prompts must be wrapped in `_safe()` / `<brain_data>` tags with `</brain_data>` escaped
- **VAPID assert** — no bare `assert` in push_service.py; use explicit `ValueError` instead
- **Sensitive data in responses** — no plaintext passwords, JWT secrets, or private keys in any API response

## 2. Architecture

Check for:

- **Layering** — services must not import from routers; routers import services, not the other way
- **Atomic writes** — every write to a brain file must use `write_json()` or `write_markdown()` from `services/file_service.py`; no bare `open(..., 'w')` or `.write_text()` on brain paths
- **Module registry sync** — `ALL_MODULES` in `app/frontend/src/lib/constants.js` and `VALID_MODULE_IDS` in `app/backend/routers/auth.py` must contain exactly the same module IDs
- **Route registration** — every router in `app/backend/routers/` must be registered in `app/backend/main.py`
- **Async consistency** — no synchronous blocking calls (file I/O, HTTP, AI SDK calls) inside `async def` route handlers without `asyncio.to_thread()`; `services/ai_provider.py` wraps this centrally
- **Error handling** — routers raise `HTTPException`; services raise `ValueError`; nothing swallowed silently

## 3. Strategy and Product Logic

Check for:

- **Module guard completeness** — for every module in `ALL_MODULES`, verify:
  - Backend routes have `require_module(module_id)` applied
  - Frontend routes in `App.jsx` are wrapped in `<ModuleRoute moduleId="...">` so disabled modules block direct URL access, not just hide nav links
- **api.js completeness** — every backend route has a corresponding method in `app/frontend/src/lib/api.js`; no orphaned methods pointing to missing routes
- **Feature completeness** — no page in `src/pages/` that imports from `api.js` and calls an endpoint that doesn't exist in the backend
- **Data shape consistency** — fields the frontend reads from API responses (e.g. `me.disabled_modules`, `task.due_time`, `task.created_by`) must be returned by the backend

## 4. Code Logic

Check for:

- **Status comparisons** — `task.status === 'done'` not `task.status !== 'pending'`; the latter catches unknown statuses incorrectly
- **Date construction** — overdue/today comparisons must use local date components (`getFullYear()`, `getMonth()`, `getDate()`), not `toISOString().split('T')[0]` which converts to UTC and gives wrong dates for UTC+ users
- **Sort safety** — `Array.indexOf()` returns -1 for missing values; always provide a fallback (e.g. `i === -1 ? 999 : i`) before using the result in a sort comparator
- **State cleanup** — modal close handlers reset both `showModal` and `editTask`; filter changes don't leave stale selections
- **Stale closures** — `useEffect` with empty dependency array that reads state will capture the initial value; verify polling intervals reference fresh state

---

## Output format

Report each finding as:

```
[SEVERITY] [CATEGORY] [file:line]
Issue: <what is wrong>
Fix: <what to change>
```

Severity levels: `CRITICAL` / `HIGH` / `MEDIUM` / `LOW`

Group by section (Security, Architecture, Strategy, Logic). Start with the highest severity items.

After all findings, output a summary:

```
DIAGNOSTIC SUMMARY
------------------
Critical: X
High:     X
Medium:   X
Low:      X
Overall:  CLEAN | NEEDS ATTENTION
```

`CLEAN` means no CRITICAL or HIGH findings. `NEEDS ATTENTION` means at least one CRITICAL or HIGH.

---

## False positive guide

These are by design — do not flag them:

- `GET /push/vapid-key` has no auth: VAPID public keys are intentionally public; service workers need them before a session exists
- `GET /auth/status` is unauthenticated: the login page calls it before the user is logged in; it is rate-limited
- `_HOUSEHOLD = "_household"` used as a username in shared.py: this is the household namespace, not a real user account
- `SameSite=strict` on auth cookie: intentionally strict
- Email addresses returned to admins in `GET /auth/users`: admins need this to manage accounts
- `settings.brain_path` patched in tests via `conftest.py` brain fixture: this is the correct test isolation pattern
