# LogCoreOS API Reference

Base URL: `/api/v1`

All authenticated endpoints require `Authorization: Bearer <token>`.

### `X-Workspace` header

Data endpoints (Tasks, Calendar, Notes, Journal) respect the `X-Workspace` header to route reads and writes to the correct workspace path:

| Value | Path prefix |
|-------|-------------|
| `personal` (default) | `brain/USERS/{name}/` |
| `business` | `brain/USERS/{name}/Business/` |

Omitting the header or sending an invalid value defaults to `personal`. The frontend injects this header automatically via `api.js` `headers()` based on the active workspace in `localStorage`.

---

## Auth

### `GET /auth/status`
Public. Returns whether self-registration is open.

**Response**
```json
{ "registration_open": true }
```

### `POST /auth/register`
Create an account. Requires admin token when registration is closed (except for the very first user).

**Body**
```json
{
  "email": "user@example.com",
  "password": "mypassword",
  "name": "Alice",
  "session_minutes": 10080
}
```

**Response**
```json
{
  "id": "uuid",
  "name": "Alice",
  "role": "member",
  "disabled_modules": [],
  "timezone": "UTC",
  "accent_color": null,
  "dark_mode": "system",
  "background": null,
  "density": "comfortable",
  "corner_style": "rounded"
}
```

### `POST /auth/login`
**Body**
```json
{ "email": "user@example.com", "password": "mypassword" }
```

**Response** — same shape as register.

### `POST /auth/logout`
Revokes the current token. Auth required.

**Response** `{ "ok": true }`

### `GET /auth/me`
Returns current user's profile.

**Response**
```json
{
  "id": "uuid",
  "name": "Alice",
  "role": "member",
  "notification_channel": "lc-abc123",
  "session_minutes": 10080,
  "timezone": "America/Chicago",
  "workspaces": ["personal"],
  "disabled_modules": [],
  "pool_edit": [],
  "accent_color": "#f97316",
  "dark_mode": "system",
  "background": "gradient:midnight",
  "density": "comfortable",
  "corner_style": "rounded",
  "shortcuts": { "personal": ["dashboard", "tasks", "chat"] }
}
```

`workspaces` — list of workspaces the user has access to. Possible values: `"personal"`, `"business"`. Defaults to `["personal"]` if absent in auth.json. When a user has both, the frontend shows a toggle pill in the sidebar.

`shortcuts` — workspace-keyed dict of pinned sidebar shortcut module IDs, e.g. `{"personal": ["dashboard", "tasks", "chat"], "business": ["dashboard", "team", "automations"]}`. Each workspace list is capped at 4 entries. Defaults to `{}` (frontend falls back to `DEFAULT_SHORTCUTS`).

### `PATCH /auth/me`
Update own profile. All fields optional.

**Body**
```json
{
  "timezone": "America/New_York",
  "accent_color": "#3b82f6",
  "dark_mode": "dark",
  "background": "gradient:sunset",
  "density": "compact",
  "corner_style": "sharp",
  "shortcuts": { "personal": ["dashboard", "tasks", "chat"], "business": ["dashboard", "team", "automations"] }
}
```

Valid values:
- `dark_mode`: `"system"` | `"light"` | `"dark"`
- `background`: `"none"` | `"uploaded"` | `"gradient:<id>"` where id ∈ `{none, midnight, sunset, forest, ocean, aurora, dusk}`
- `density`: `"comfortable"` | `"compact"`
- `corner_style`: `"rounded"` | `"sharp"`
- `accent_color`: any 6-digit hex like `#f97316`
- `shortcuts`: workspace-keyed dict of module ID arrays; each list is validated against known module IDs and capped at 4 entries. Allowed workspace keys: `"personal"`, `"business"`.

**Response** `{ "ok": true, ...updated_fields }`

### `POST /auth/me/background`
Upload a custom background image. Max 5 MB. Accepted types: JPEG, PNG, WebP, AVIF.

**Body** — `multipart/form-data` with field `file`.

Sets `background` to `"uploaded"` on the user record. File stored at `brain/USERS/{name}/background.{ext}`.

**Response** `{ "ok": true }`

### `GET /auth/me/background`
Serve the user's uploaded background image. Returns the image file directly.

**Response** — image bytes with the appropriate `Content-Type`.

**Error** `404` if no image has been uploaded.

### `DELETE /auth/me/background`
Remove the uploaded background image and clear the `background` field.

**Response** `204 No Content`

### `PATCH /auth/session`
Update own session length.

**Body** `{ "session_minutes": 43200 }`

**Response** `{ "ok": true, "session_minutes": 43200 }`

### `GET /auth/today`
Returns today's date in the user's timezone.

**Response** `{ "today": "2024-06-01" }`

---

## Admin — Users

Requires admin role.

### `GET /auth/users`
List all users (safe fields only).

**Response**
```json
[
  {
    "id": "uuid",
    "name": "Alice",
    "email": "alice@example.com",
    "role": "member",
    "timezone": "UTC",
    "disabled_modules": [],
    "created_at": "2024-01-01T00:00:00+00:00"
  }
]
```

### `PATCH /auth/users/{user_id}`
Update a user's profile (timezone, etc.).

**Body** `{ "timezone": "America/Chicago" }`

### `PATCH /auth/users/{user_id}/role`
Promote or demote a user.

**Body** `{ "role": "admin" }` or `{ "role": "member" }`

**Response** `{ "ok": true, "role": "admin" }`

### `PATCH /auth/users/{user_id}/modules`
Set which modules are disabled for a user.

**Body** `{ "disabled_modules": ["chat", "brain"] }`

**Response** `{ "ok": true, "disabled_modules": ["chat", "brain"] }`

### `GET /auth/admin/settings`
Get runtime admin settings.

**Response** `{ "allow_open_registration": false, "enabled_workspaces": ["personal", "business"] }`

### `PATCH /auth/admin/settings`
Update runtime admin settings. All fields optional — only send what changes.

**Body** `{ "allow_open_registration": true }` and/or `{ "enabled_workspaces": ["personal"] }`

`enabled_workspaces` — instance-wide list of workspaces available on this install (subset of `["personal", "business"]`, never empty). Hiding a workspace removes it for **everyone, including admins**: `get_current_user()` intersects each user's `workspaces` with this list. Used for personal-only or business-only deployments.

### `GET /auth/admin/ai-settings`
Get AI provider configuration.

**Response** `{ "provider": "anthropic", "model": "claude-sonnet-4-6", "api_key_set": true }`

### `PATCH /auth/admin/ai-settings`
Update AI provider configuration.

**Body** `{ "provider": "anthropic", "model": "claude-sonnet-4-6", "api_key": "sk-..." }`

### `GET /auth/admin/search-settings`
Get Tavily web search configuration.

**Response** `{ "tavily_key_set": true }`

### `PATCH /auth/admin/search-settings`
Update Tavily API key.

**Body** `{ "tavily_key": "tvly-..." }`

### `GET /auth/admin/hosting-settings`
Get current hosting configuration (reads from `brain/hosting.json` with env var fallback).

**Response** `{ "cookie_secure": false, "trust_proxy_headers": false, "domain_url": "" }`

### `PATCH /auth/admin/hosting-settings`
Update hosting configuration. Takes effect immediately without a restart.

**Body** `{ "cookie_secure": true, "trust_proxy_headers": true, "domain_url": "https://logcore.example.com" }`

### `POST /auth/admin/users`
Create a new user (admin only).

**Body**
```json
{
  "email": "bob@example.com",
  "password": "secret",
  "name": "Bob",
  "role": "member",
  "workspaces": ["personal"]
}
```

`workspaces` defaults to `["personal"]` if omitted.

### `PATCH /auth/admin/users/{user_id}/workspaces`
Set which workspaces a user can access. Admin only.

**Body** `{ "workspaces": ["personal", "business"] }`

Valid workspace values: `"personal"`, `"business"`. At least one workspace must remain enabled. Workspaces disabled instance-wide (see `enabled_workspaces`) are rejected with 400.

**Response** `{ "ok": true, "workspaces": ["personal", "business"] }`

### `PATCH /auth/admin/users/{user_id}/pool-edit`
Grant or revoke pool-management rights for a user. Admin only.

**Body** `{ "pool_edit": ["household", "team"] }`

Valid pool values: `"household"`, `"team"`. A grant lets the user add/edit/delete events and add/edit/delete/assign tasks in that shared pool — full parity with an admin. Default is `[]` (no grant); admins always have full access regardless. This is a dedicated per-user grant, **not** part of `disabled_modules` (that union model can only remove access, never grant it).

**Response** `{ "ok": true, "pool_edit": ["household"] }`

### `PATCH /auth/admin/users/{user_id}/workspace-modules`
Set which modules are disabled for a specific workspace. Admin only.

**Body**
```json
{
  "workspace": "business",
  "disabled_modules": ["notes", "journal"]
}
```

Stores workspace-keyed disabled modules in auth.json. Backward compat: if `disabled_modules` is still a flat list (pre-workspace users), it is treated as applying to both workspaces until overwritten.

**Response** `{ "ok": true }`

### `DELETE /auth/admin/users/{user_id}`
Delete a user and their Brain folder.

---

## Tasks

### `GET /tasks`
List all tasks for the current user.

**Response** — array of task objects.

### `GET /tasks/top3`
Return the top 3 scored pending tasks.

### `GET /tasks/scored`
Return all pending tasks sorted by score descending.

### `GET /tasks/history`
Return completed tasks (most recent first).

**Query params**
- `limit` — integer 1–500, default 50
- `offset` — integer ≥ 0, default 0

### `GET /tasks/assigned`
Return pending tasks from pool (household or team) that are assigned to the current user. Personal workspace returns tasks from the household pool; business workspace returns tasks from the team pool.

**Response** — array of task objects. Each task has a `_source` field: `"household"` or `"team"`.

```json
[
  { "id": "...", "title": "Grocery run", "_source": "household", ... }
]
```

### `POST /tasks`
Create a task.

**Body**
```json
{
  "title": "Read the Bible",
  "category": "God",
  "priority": "High",
  "type": "recurring",
  "recurrence": "daily",
  "due_date": "2024-06-01",
  "due_time": "07:00",
  "notes": "Morning reading"
}
```

Fields `due_date`, `due_time`, `notes`, `recurrence` are optional. `due_time` requires `due_date`.

**Done-task retention:** Non-recurring tasks marked done stay in `/tasks` until the nightly 00:01 scheduler archives them to history. Recurring tasks are never archived.

**Un-marking done:** Send `{ "status": "pending" }` to revert a completed task. `completed_at` is cleared automatically; recurring tasks also have `streak_count` decremented and `last_completed_date` cleared.

### `PATCH /tasks/{task_id}`
Update a task. Only send fields you want to change. Pass `null` to clear optional fields.

**Body** (all fields optional)
```json
{
  "status": "done",
  "due_date": null,
  "notes": "Updated note"
}
```

### `DELETE /tasks/{task_id}`
Delete a task permanently.

**Response** `{ "ok": true }`

---

## Priorities

### `GET /priorities`
Get the current category priority order and profile order.

**Response**
```json
{
  "order": ["God", "Family", "Job"],
  "profile_order": ["God", "Family", "Job", "Personal Growth", "Hobbies"]
}
```

### `POST /priorities/override`
Set today's priority order override.

**Body** `{ "order": ["Job", "God", "Family"] }`

### `GET /priorities/pool`
Get the category priority order for both pool pseudo-users (`_household` and `_team`). Admin only.

**Response**
```json
{
  "household": ["Family", "Home", "Errands", "Health", "Finance", "Other"],
  "team": ["Client Delivery", "Revenue", "Operations", "Marketing", "HR & People", "Finance", "Product", "Strategy"]
}
```

### `PUT /priorities/pool`
Update the category priority order for a pool pseudo-user. Admin only.

**Body** `{ "pool": "household", "order": ["Family", "Home", "Errands"] }`

Valid `pool` values: `"household"`, `"team"`.

**Response** `{ "ok": true }`

---

## Chat

### `POST /chat`
Send a message to the AI. Returns a streaming response with step trace.

**Body**
```json
{
  "message": "What should I focus on today?",
  "history": [
    { "role": "user", "content": "Hi" },
    { "role": "assistant", "content": "Hello! How can I help?" }
  ],
  "mode": "auto",
  "cross_workspace": false
}
```

- `mode`: `"approve"` (default) | `"plan"` | `"auto"` | `"research"`. Approve mode runs reads freely but pauses before any write: the response has `mode: "awaiting_approval"` and `steps` containing `pending_write` entries (`{ type, tool, input, step }`); nothing is executed until the user approves (the frontend re-sends as a one-turn `auto` request). Plan mode proposes a whole plan before executing. Research mode adds Tavily web search, read-only.
- `cross_workspace`: when `true` and the user has both workspaces, the AI searches both personal and business Brain paths (results prefixed `personal/` or `business/`). Only available to dual-workspace users.

Rate limited: 20 messages per minute per IP.

### `POST /chat/save`
Create or overwrite a chat archive file.

**Body** `{ "history": [...], "name": "Optional title", "filename": "2026-07-02_12-00-00.md" }`

- `filename`: if provided, overwrites that file (for continued chat edits). If omitted, creates a new timestamped file.
- `name`: optional title override; auto-generated from the first user message if absent.

**Response** `{ "filename": "2026-07-02_12-00-00.md", "title": "My chat title" }`

### `GET /chat/saved`
List all saved chat `.md` files for the current user in the active workspace, newest first.

**Response** — array of `{ "filename": "...", "title": "..." }` objects.

### `DELETE /chat/saved/{filename}`
Delete a saved chat file.

**Response** `{ "ok": true }`

### `POST /chat/save-memory`
Extract key facts from a conversation and append them to the user's long-term memory.

**Body** `{ "history": [...] }`

**Response** `{ "ok": true }`

### `GET /chat/runs`
List recent agent runs (tool-using runs only) for the current user.

**Response** — array of run objects `{ "id": "...", "timestamp": "...", "steps": [...] }`.

### `GET /chat/runs/{run_id}`
Get a specific agent run by ID.

**Response** — single run object. `404` if not found.

---

## Brain

### `GET /brain/files`
List all files in the user's brain folder.

### `GET /brain/files/{path}`
Read a brain file. Path is relative to the user's brain folder.

### `PUT /brain/files/{path}`
Update a brain file. The file must already exist.

**Body** `{ "content": "# My Profile\n\n..." }`

---

## Setup

### `GET /setup/status`
Check if the current user's brain folder is set up.

**Response** `{ "setup_complete": true }`

### `POST /setup`
Run first-time setup (copies the brain template for this user).

**Body**
```json
{
  "priorities": ["God", "Family", "Job", "Personal Growth", "Hobbies"],
  "timezone": "America/Chicago"
}
```

---

## User

### `GET /user/export`
Download the current user's entire brain folder as a `.zip` file.

**Response** — `application/zip` stream with header `Content-Disposition: attachment; filename="Name_brain.zip"`.

---

## Notes

All endpoints require the `notes` module to be enabled.

### `GET /notes`
List all notes files and folders for the current user.

### `GET /notes/file/{path}`
Read a note file. Path is relative to the user's Notes folder.

### `POST /notes/file`
Create a new note file.

**Body** `{ "path": "ideas/startup.md", "content": "# Ideas\n\n..." }`

### `PUT /notes/file/{path}`
Update an existing note file.

**Body** `{ "content": "# Updated\n\n..." }`

### `DELETE /notes/file/{path}`
Delete a note file.

### `POST /notes/folder`
Create a new folder.

**Body** `{ "path": "projects/logcore" }`

### `DELETE /notes/folder/{path}`
Delete a folder and all its contents.

### `POST /notes/move`
Move or rename a file or folder.

**Body** `{ "from": "old/path.md", "to": "new/path.md" }`

---

## Journal

All endpoints require the `journal` module to be enabled.

### `GET /journal`
List all journal entry dates for the current user.

### `GET /journal/{date}`
Read a journal entry. `date` format: `YYYY-MM-DD`.

### `PUT /journal/{date}`
Write or replace a journal entry.

**Body** `{ "content": "# Today\n\n..." }`

### `DELETE /journal/{date}`
Delete a journal entry.

---

## Calendar

All endpoints require the `calendar` module to be enabled.

### `GET /calendar/tasks`
Get tasks that have a due date (for calendar display).

### `GET /calendar/events`
List calendar events for the current user.

### `POST /calendar/events`
Create a calendar event.

**Body**
```json
{
  "title": "Family dinner",
  "date": "2026-06-25",
  "color": "#f97316",
  "notes": "Book the restaurant"
}
```

### `GET /calendar/events/{event_id}`
Get a single event.

### `PATCH /calendar/events/{event_id}`
Update a calendar event. Only send fields to change.

### `DELETE /calendar/events/{event_id}`
Delete a calendar event.

---

## Profile

### `GET /profile`
Read the current user's `Profile.md` content.

**Response** `{ "content": "# Profile\n\n..." }`

### `PUT /profile`
Replace the current user's `Profile.md`.

**Body** `{ "content": "# Profile\n\n..." }`

---

## Suggestions

### `GET /suggestions`
List active proactive suggestions for the current user.

### `PUT /suggestions/{suggestion_id}`
Update a suggestion (e.g., dismiss or snooze).

### `POST /suggestions/{suggestion_id}/run`
Execute a suggestion action.

### `DELETE /suggestions/custom/{suggestion_id}`
Delete a custom suggestion.

### `GET /suggestions/notifications`
List the notification inbox for the current user.

### `POST /suggestions/notifications/{notif_id}/read`
Mark a notification as read.

### `DELETE /suggestions/notifications`
Clear all notifications.

---

## Shared (Household)

Endpoints for the household pool — tasks and events shared across all household members. Router mounted at `/api/v1/shared`.

Any authenticated household member may **read** tasks and events. **All writes** (create/update/delete tasks and events, assign) require pool-management rights: admin role, or the `household` grant in the user's `pool_edit`. See `PATCH /auth/admin/users/{id}/pool-edit`.

### `GET /shared/members`
Member names for the assignment dropdown. Requires household pool-management rights (admin or `household` grant).

**Response** — `[{ "name": "Alice" }, ...]`

### `GET /shared/tasks`
List all shared tasks. Returns all tasks regardless of due date or status.

### `POST /shared/tasks`
Create a shared task. `created_by` is set automatically from the auth token.

**Body**
```json
{
  "title": "Grocery run",
  "category": "Family",
  "priority": "Medium",
  "type": "todo",
  "due_date": "2026-07-01",
  "assigned_to": "Alice"
}
```

`assigned_to` is optional. When set to a user's display name, that user sees the task in their personal Tasks page (filtered client-side) and calendar grid, both tagged with a 🏠 badge.

### `PATCH /shared/tasks/{task_id}`
Update a shared task. Setting `status` to `done` or `skipped` records `completed_by`. Setting `status` to `pending` un-marks a completed task (clears `completed_at`; decrements streak for recurring).

### `DELETE /shared/tasks/{task_id}`
Delete a shared task.

### `GET /shared/events`
List shared calendar events (household pool). Visible on every member's personal calendar when the 🏠 toggle is on.

### `POST /shared/events`
Create a shared calendar event. Requires household pool-management rights (admin or `household` grant). `created_by` set automatically.

Household events are also created indirectly by the **"Add to Household"** toggle in the personal calendar's EventModal — this deletes the personal event and creates a household event in one operation. The toggle is only shown to users with pool-management rights.

### `PATCH /shared/events/{event_id}`
Update a shared event. **Pool managers only** (admin or `household` grant).

### `DELETE /shared/events/{event_id}`
Delete a shared event. **Pool managers only** (admin or `household` grant). Returns `204 No Content`.

---

## Team (Business Pool)

Endpoints for the business team pool — tasks and events shared across all business workspace members. Router mounted at `/api/v1/team`. Requires the `team` module to be enabled.

The team pool is completely isolated from the household pool (`/shared`). They share the same task/event shape but use separate pseudo-user stores (`_team` vs `_household`) and separate router code — there is no code path that can cross-contaminate the two pools.

Any authenticated team member may **read** tasks and events. **All writes** require pool-management rights: admin role, or the `team` grant in the user's `pool_edit`.

### `GET /team/members`
Member names for the assignment dropdown. Requires team pool-management rights (admin or `team` grant).

**Response** — `[{ "name": "Bob" }, ...]`

### `GET /team/tasks`
List all team tasks.

### `POST /team/tasks`
Create a team task. `created_by` is set automatically from the auth token.

**Body**
```json
{
  "title": "Quarterly report",
  "category": "LogCore",
  "priority": "High",
  "type": "todo",
  "due_date": "2026-07-15",
  "assigned_to": "Bob"
}
```

### `PATCH /team/tasks/{task_id}`
Update a team task.

### `DELETE /team/tasks/{task_id}`
Delete a team task.

### `GET /team/events`
List team calendar events.

### `POST /team/events`
Create a team calendar event. Requires team pool-management rights (admin or `team` grant).

### `PATCH /team/events/{event_id}`
Update a team event. **Pool managers only** (admin or `team` grant).

### `DELETE /team/events/{event_id}`
Delete a team event. **Pool managers only** (admin or `team` grant). Returns `204 No Content`.

---

## Assets

Router mounted at `/api/v1/assets`. Requires the `assets` module (both workspaces; workspace-scoped via `X-Workspace`). Assets form a tree via `parent_id`; every object is built from an admin-curated **template** (ordered typed fields).

### Templates

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `GET` | `/assets/templates` | module users | list templates |
| `POST` | `/assets/templates` | admin | `{key, label, icon, fields:[{key,label,type,options?,default?}]}`; types: text/number/date/boolean/select; key slug immutable |
| `POST` | `/assets/templates/example` | admin | insert an editable example template |
| `PATCH` | `/assets/templates/{key}` | admin | replace label/icon/fields |
| `DELETE` | `/assets/templates/{key}` | admin | `409` if any asset still uses it |

### Assets

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `GET` | `/assets` | module users | own + workspace pool + shared-to-me (annotated `_owner`/`_access`); `?template=`, `?include_archived=true` |
| `POST` | `/assets` | module users | `{template, name, parent_id?, fields?, notes?, owner: "me"\|"pool"}`; `pool` needs admin or `pool_edit` grant |
| `GET`/`PATCH` | `/assets/{id}` | per access | PATCH allowed for owner/edit-share/pool manager; records history |
| `POST` | `/assets/{id}/archive` · `/unarchive` | owner / pool manager | archiving hides the whole subtree |
| `DELETE` | `/assets/{id}` | **admin** | `409` if it has children; removes attachment files |
| `POST` | `/assets/{id}/convert` | **admin** | `{target:"pool"}` — move subtree + files to `_team`/`_household`; strips shares |
| `PUT` | `/assets/{id}/access` | owner (pool: admin/grant) | `{shared_with?:[{target,access}], hidden_from?:[names]}`; pool assets accept `hidden_from` only; `hidden_from` beats shares and is enforced server-side |
| `POST` | `/assets/{id}/files` | owner/edit-share | multipart `file`; jpeg/png/webp/avif/pdf; 10 MB; ≤20 per asset |
| `GET` | `/assets/{id}/files/{file_id}` | any access | binary response |
| `DELETE` | `/assets/{id}/files/{file_id}` | owner/edit-share | `204` |

### Automation API (n8n)

Token auth via `X-Automation-Token` header — no JWT. Token lives in `brain/_system/automations_config.json`; admins reveal/rotate it in Admin → n8n or via `GET /assets/automation/token` / `POST /assets/automation/token/rotate` (admin JWT).

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/assets/automation/assets?user=&workspace=&template=` | `user` may be a real user or `_team`/`_household` |
| `POST` | `/assets/automation/assets` | `{user, workspace, template, name, parent_id?, fields?, notes?}` |
| `PATCH` | `/assets/automation/assets/{id}` | `{user, workspace, name?, fields?, notes?}` |

### Task linking

`POST /tasks` and `PATCH /tasks/{id}` accept an optional `asset_id` field linking the task to an asset.

---

## Push Notifications

### `GET /push/vapid-key`
Get the VAPID public key for web push subscription.

### `POST /push/subscribe`
Register a push subscription.

**Body** — Web Push subscription object from the browser.

### `DELETE /push/subscribe`
Remove the current push subscription.

### `POST /push/test`
Send a test push notification to the current user.

---

## Automations (n8n)

Router mounted at `/api/v1/automations`. Requires the `automations` module to be enabled (or `automations_business` for business-scope workflows).

### Admin — n8n Config

#### `GET /automations/n8n/status`
Get n8n connection status and workflow count. Admin only.

#### `POST /automations/n8n/config`
Save n8n URL and API key. Admin only.

**Body** `{ "url": "http://logcore-n8n:5678", "api_key": "n8n_api_..." }`

#### `POST /automations/n8n/sync-workflows`
Trigger an immediate business workflow sync from the remote stub source. Admin only.

#### `POST /automations/n8n/sync-secrets`
Re-pull Infisical secrets into `docker/n8n.env` and restart the n8n container. Admin only.

### Workflow Management

#### `GET /automations`
List workflows for the current user. Returns personal or business workflows based on the active workspace.

#### `POST /automations/import`
Import a workflow JSON into n8n and record it in the workflow index.

**Body** — `multipart/form-data` with `file` (workflow JSON) and optional `scope` (`"personal"` | `"business"`).

#### `DELETE /automations/{record_id}`
Delete a workflow record and remove it from n8n. Returns `204 No Content`.

#### `POST /automations/{record_id}/run`
Trigger a workflow execution.

**Response** `{ "ok": true, "execution_id": "..." }`

#### `POST /automations/{record_id}/activate`
Activate a workflow in n8n.

#### `POST /automations/{record_id}/deactivate`
Deactivate a workflow in n8n.

#### `GET /automations/{record_id}/logs`
Get recent execution logs for a workflow.

---

## Smart Home (Home Assistant)

Router mounted at `/api/v1/home`. Requires the `home` module to be enabled (personal workspace only).

### Admin — HA Config

#### `GET /home/status`
Get Home Assistant connection status. Returns whether HA is configured and reachable.

#### `POST /home/config`
Save Home Assistant URL and long-lived token. Admin only. Config stored at `brain/_system/ha_config.json`.

**Body** `{ "url": "http://homeassistant.local:8123", "token": "eyJ..." }`

### Entities

#### `GET /home/entities`
List all entity states from Home Assistant.

#### `GET /home/entities/{entity_id}`
Get state of a single entity.

#### `POST /home/entities/{entity_id}/call`
Call a Home Assistant service on an entity (e.g., `light.turn_on`).

**Body** `{ "service": "turn_on", "data": { "brightness": 200 } }`

#### `GET /home/areas`
List all areas defined in Home Assistant.

### Scenes & Automations

#### `GET /home/scenes`
List all scenes.

#### `POST /home/scenes/{entity_id}/activate`
Activate a scene.

#### `GET /home/automations`
List all HA automations.

#### `POST /home/automations/{entity_id}/trigger`
Trigger a HA automation.

### Favourites

#### `GET /home/favourites`
Get the current user's pinned favourite entity IDs.

**Response** `{ "favourites": ["light.living_room", "switch.fan"] }`

#### `PUT /home/favourites`
Replace the current user's favourite entity list.

**Body** `{ "favourites": ["light.living_room", "switch.fan"] }`

---

## Admin — Infisical

These endpoints are mounted under `/api/v1/auth`. Admin only.

### `GET /auth/admin/infisical-status`
Get Infisical integration status (whether a token is configured and from which source).

### `PATCH /auth/admin/infisical-token`
Set or update the Infisical token.

**Body** `{ "token": "st...." }`

### `DELETE /auth/admin/infisical-token`
Clear the file-stored Infisical token. Only file-sourced tokens can be cleared via UI; env-var tokens cannot.

---

## Admin — Feature Roles

These endpoints are mounted under `/api/v1/auth`. Admin only.

### `GET /auth/admin/features`
Get all feature roles and their default disabled modules.

**Response** `{ "roles": { "cleaner": { "disabled_modules": ["chat", "brain", ...] }, ... } }`

### `POST /auth/admin/features/roles`
Create a new custom feature role.

**Body** `{ "name": "cleaner", "disabled_modules": ["chat", "brain", "notes"] }`

### `PATCH /auth/admin/features/roles/{role_name}`
Update a feature role's disabled module list.

**Body** `{ "disabled_modules": ["chat"] }`

### `DELETE /auth/admin/features/roles/{role_name}`
Delete a custom feature role.

### `PATCH /auth/admin/features/users/{user_id}/role`
Assign a feature role to a user.

**Body** `{ "feature_role": "cleaner" }`

---

## Health

### `GET /health`
Returns `{ "status": "ok" }`. No auth required. Used by Docker healthcheck.
