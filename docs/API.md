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
| `GET` | `/assets/templates` | module users | templates the viewer can build from: role-permitted global + own personal + accepted-shared (each tagged `_scope`: global/own/shared). A default global 📁 **Folder** template (key `folder`, no custom fields) is seeded once by migration `m006` |
| `POST` | `/assets/templates` | module users | `{key, label, icon, fields:[...], owner:"me"\|"global"}`; `global` = admin only; key slug immutable, unique within owner |
| `POST` | `/assets/templates/example?owner=me\|global` | module users (global=admin) | insert an editable example template |
| `PATCH` | `/assets/templates/{id}` | owner / admin (global) | replace label/icon/fields (+ `restrict_roles` for global) |
| `DELETE` | `/assets/templates/{id}` | owner / admin (global) | `409` if any asset still uses it |
| `PUT` | `/assets/templates/{id}/access` | owner / admin (global) | personal: `{shared_with:[{target}]}` (request handshake); global: `{restrict_roles:[...]}` |
| `POST` | `/assets/templates/{id}/leave` | recipient | remove self from a shared personal template (global can't be left) |
| `GET` | `/assets/roles` | module users | feature-role names for the share-by-role picker |
| `POST` | `/assets/shares/respond` | recipient | `{notif_id, accept}` — accept/decline a share request (asset or template) delivered as an actionable notification |

### Assets

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `GET` | `/assets` | module users | own + workspace pool + shared-to-me (annotated `_owner`/`_access`; contribute-level entries also carry `_caps`); `?template=`, `?include_archived=true`. Share resolution is index-routed (`assets_share_index.json`) |
| `GET` | `/assets/members` | module users | member display **names only** for share/hide selectors |
| `POST` | `/assets` | module users | `{template_id\|template, name, parent_id?, fields?, notes?, owner:"me"\|"pool"}`; `pool` needs admin/`pool_edit`. `parent_id` set → child created in the **parent's store** (requires edit access) inheriting its `shared_with`+`hidden_from` (the "group" mechanic). Asset responses embed the resolved template as `_template`. When the record is created outside the caller's own store, the response carries `_owner` (`team`/`household`/owner name) + `_access: "edit"` like list/find responses |
| `PUT` | `/assets/{id}/access` | owner (pool: admin/grant) | share entries are **requests**: `{shared_with:[{target,access,caps?}], hidden_from?, contributors?, cascade=true}`; each new target (user/team/household/role) is notified and the asset stays hidden until they accept. `access` is `read` \| `contribute` \| `edit` — **contribute** carries a `caps` object `{fields:[keys], add:[comments\|files\|children]}` naming exactly which template fields the person may change and what they may add (missing caps default to comment-only). **Resolution is specificity-based: an entry targeting the viewer by name fully overrides any group/role entry** (so one member of an edit-shared group can be restricted to contribute); union only happens between same-level contribute entries. `hidden_from` accepts user names **and dynamic `role:<feature_role>` entries** (hides from everyone holding that role, future assignees included). `contributors` (pool assets only, admin/pool-manager): `[{target: team\|household\|name, caps}]` — capability grants without the accept handshake, since pool assets are already workspace-visible; `shared_with` on pool assets stays rejected. A **by-name contributor entry also downgrades a non-admin `pool_edit` manager** to those caps on that asset (group entries never downgrade managers; admins are never restricted) |
| `POST` | `/assets/{id}/comments` | edit-level, or contribute with `comments` cap | `{text}` (≤2000 chars) → appended to the asset's attributed comment log (cap 100, oldest trimmed). `400` while `comments_hidden` is on. Notifies every edit-level user (owner, accepted edit shares; pool: admins + `pool_edit` grantees) except the author and anyone who muted the asset/an ancestor — in-app notification with an `open_asset` action (NotifBell "View →" jumps to `/assets?asset=<id>`) plus ntfy/web push with the same deep link |
| `DELETE` | `/assets/{id}/comments/{comment_id}` | **admin only** | comments are an audit-style log — authors/owners cannot delete; owners hide the section instead. `204` |
| `PUT` | `/assets/{id}/comments/visibility` | edit-level users | `{hidden: bool}` — turn comments off (or back on) for ALL users on this asset (set from the edit page); data kept, posting blocked while off. Per-user collapsing of the section is frontend-only state (resets on reopen) |
| `GET` | `/assets/{id}/mute` | any viewer | viewer's own comment-notification state: `{muted, self, via, via_name}` — `via` names the node whose mute covers this asset (self or an ancestor) |
| `PUT` | `/assets/{id}/mute` | any viewer | `{muted: bool}` — per-user opt in/out of comment notifications for this asset **and its whole subtree** (stored per user in `USERS/{name}/Assets/comment_mutes.json`; delivery walks ancestors). Returns the new state |
| `POST` | `/assets/{id}/leave` | share recipient | remove self from an asset shared with you |
| `GET`/`PATCH` | `/assets/{id}` | per access | PATCH allowed for owner/edit-share/pool manager; records history. Re-parent (move) is same-owner only |
| `POST` | `/assets/{id}/archive` · `/unarchive` | owner / pool manager | **per-node**; `?cascade=true` (un)archives the whole subtree. Archiving only a parent leaves its children active (they float to top level) |
| `DELETE` | `/assets/{id}` | owner (personal) / **admin** (pool) | `409` if it has children; removes attachment files |
| `POST` | `/assets/{id}/convert` | **admin** | `{target:"pool"}` — move subtree + files to `_team`/`_household`; strips shares |
| `POST` | `/assets/{id}/files` | owner/edit-share | multipart `file`; jpeg/png/webp/avif/pdf; 10 MB; ≤20 per asset |
| `GET` | `/assets/{id}/files/{file_id}` | any access | binary response |
| `DELETE` | `/assets/{id}/files/{file_id}` | owner/edit-share | `204` |

### Automation API (n8n)

Token auth via `X-Automation-Token` header — no JWT. Token lives in `brain/_system/automations_config.json`; admins reveal/rotate it in Admin → n8n or via `GET /assets/automation/token` / `POST /assets/automation/token/rotate` (admin JWT).

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/assets/automation/assets?user=&workspace=&template=` | `user` may be a real user or `_team`/`_household` |
| `POST` | `/assets/automation/assets` | `{user, workspace, template, name, parent_id?, fields?, notes?}` |
| `PATCH` | `/assets/automation/assets/{id}` | **Edit an asset from a workflow**: `{user, workspace, name?, fields?, notes?}`. `fields` merges per key (send `null` to clear a value); values are validated against the asset's template exactly like user edits; the change lands in the asset's `history` attributed `"automation"` |
| `POST` | `/assets/automation/assets/{id}/comments` | **Post a comment from a workflow**: `{user, workspace, text}` (≤2000 chars). Comment is attributed `"automation"` and triggers the same edit-level notifications as a user comment — e.g. an n8n inspection workflow posting "inspection failed" alerts the owner with a jump-to-asset button |

`user`/`workspace` on every automation call name the store the asset lives in (`user` may be `_team`/`_household` for pool assets). Rate limit 30/min. The automation token is a machine credential — **never hand it to a person**; employees use their own accounts (contribute shares / contributor grants) so writes stay attributed.

### Task linking

`POST /tasks` and `PATCH /tasks/{id}` accept an optional `asset_id` field linking the task to an asset.

---

## Finance

Router mounted at `/api/v1/finance`. Requires the `finance` module (disabled for the `guest` feature role by default; both workspaces, workspace-scoped via `X-Workspace`). All amounts are **signed integer cents**: positive = income, negative = expense.

**Books** are the top-level unit — each holds its own accounts, customizable categories (name + kind `expense|income`), and transactions (stored per-book per-year). Personal/business books are private to their owner (invisible to admins). **Pool books** (`_household` in personal ws, `_team` in business ws) are visible to every workspace member; writes are admin-only until per-book contributors ship. Book responses are annotated `_owner` (`household`/`team`; absent = own) and `_access` (`edit`/`read`); list/detail responses include computed `balances` (per account) and `total_cents` (active accounts).

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `GET` | `/finance/books?include_archived=` | module users | own + workspace-pool books with balances |
| `POST` | `/finance/books` | module users | `{name, icon?, currency?, categories?, pool?}`; `pool: true` = admin only, creates in the workspace pool |
| `GET`/`PATCH` | `/finance/books/{id}` | read / edit | PATCH: name/icon/currency/budget_warn_pct/archived/categories/tax_categories. Removing a category relabels its transactions to `""` (uncategorized) |
| `DELETE` | `/finance/books/{id}` | owner / admin (pool) | `409` while transactions exist — archive instead |
| `POST` | `/finance/books/{id}/accounts` | edit | `{name, type: checking\|savings\|credit\|cash\|other, opening_balance_cents?, opening_date?}` |
| `PATCH`/`DELETE` | `/finance/books/{id}/accounts/{aid}` | edit | DELETE `409` while the account has transactions (archive instead); archived accounts reject new transactions |
| `GET` | `/finance/books/{id}/transactions?from&to&account&category&q&limit&offset` | read | newest first; returns `{items, total}` |
| `POST` | `/finance/books/{id}/transactions` | edit | `{date, amount_cents, account_id, category?, payee?, notes?, deductible?, tax_category?}`; category must exist on the book or be `""` |
| `PATCH`/`DELETE` | `/finance/books/{id}/transactions/{tid}` | edit | date edits across a year boundary move the record between year shards transparently |
| `GET` | `/finance/books/{id}/reports/monthly?month=YYYY-MM` | read | income/expense/net + per-category breakdown, computed on read |
| `GET` | `/finance/networth` | module users | total + per-book totals across all visible books in the workspace |

### Bank sync (SimpleFIN — admin-managed) + CSV import

Bank connections use SimpleFIN Bridge **read-only** tokens. Members never enter tokens: they *request* a connection (admins get a bell/push with a View → to Admin), an admin claims the user's setup token in **Admin → Bank Connections**, then the member maps connected bank accounts onto their own book accounts from **Finance → 🏦 Bank**. The access URL lives at `brain/USERS/{name}/Finance/simplefin.json` and is only ever output by the admin reveal endpoint. Sync runs 2 min after boot + every 12 h; imported transactions land uncategorized (`category: ""`) unless a learned payee rule matches.

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `POST` | `/finance/simplefin/request` | module users | notify all admins (rate 3/hour) |
| `GET` | `/finance/simplefin/status` | module users | own sanitized status — never includes the access URL |
| `GET` | `/finance/simplefin/accounts` | module users | live list of connected bank accounts (for the mapping UI) |
| `PUT` | `/finance/simplefin/mapping` | module users | `{entries: [{simplefin_account_id, bank_name?, account_name?, target: {store: self\|household\|team, workspace, book_id, account_id}, enabled}]}` — pool targets **admin-only** |
| `GET` | `/finance/simplefin/connections` | **admin** | per-user connection status for the Admin card |
| `POST` | `/finance/simplefin/claim` | **admin** | `{user_id, setup_token}` → claims + stores the access URL for that user; notifies them (rate 5/hour) |
| `POST` | `/finance/simplefin/reveal` | **admin** | `{user_id}` → the stored access URL (rate 3/hour — the only endpoint that outputs it) |
| `DELETE` | `/finance/simplefin/{user_id}` | **admin** | disconnect (deletes the stored token; imported data stays) |
| `POST` | `/finance/simplefin/sync` | **admin** | `{user_id}` → run a sync now; returns `{created, skipped, errors?}` |
| `POST` | `/finance/books/{id}/import/csv` | edit | multipart `file` (≤5 MB) → `{headers, rows, total_rows}` preview |
| `POST` | `/finance/books/{id}/import/csv/commit` | edit | multipart `file` + form fields `account_id, date_col, amount_col, payee_col?, notes_col?, date_format?, invert_amounts?` → `{created, skipped, errors?}`; dedup by `import_hash` |
| `GET` | `/finance/books/{id}/rules` | edit | learned payee→category rules |
| `DELETE` | `/finance/books/{id}/rules/{rule_id}` | edit | forget a rule |

Rules are learned automatically when a user sets a category on an imported (`simplefin`/`csv`) transaction via `PATCH /finance/books/{id}/transactions/{tid}`.

### Planning (budgets, recurring, planned, projection)

All statuses/projections computed on read. Alerts (budget warn/over, missed bills, balance deviation) arrive via bell + push with a **View →** deep link to the book; own-store alerts go to the owner, pool-book alerts to admins.

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `GET`/`PUT` | `/finance/books/{id}/budgets` | read / edit | `{budgets: [{category, monthly_limit_cents}]}` — categories must exist on the book |
| `GET` | `/finance/books/{id}/budgets/status?month=YYYY-MM` | read | spent/remaining/pct per budgeted category. Alerts escalate none→warn (book `budget_warn_pct`, default 80)→over, once each per month |
| `GET`/`POST` | `/finance/books/{id}/recurring` | read / edit | `{name, amount_cents (signed), account_id, category?, cadence: weekly\|monthly\|yearly, next_due, autopay?}` |
| `PATCH`/`DELETE` | `/finance/books/{id}/recurring/{rid}` | edit | PATCH also takes `active` (pause/resume) |
| `GET` | `/finance/books/{id}/recurring/upcoming?days=30` | read | `{upcoming, missed}` — missed = 3+ days past due, unmatched |
| `GET`/`POST` | `/finance/books/{id}/planned` | read / edit | one-off expected items `{name, date, amount_cents, account_id}`; PATCH takes `done` |
| `PATCH`/`DELETE` | `/finance/books/{id}/planned/{pid}` | edit | |
| `GET` | `/finance/books/{id}/accounts/{aid}/projection?date=YYYY-MM-DD` | read | `{current_cents, projected_cents, items: [...]}` — current balance + recurring occurrences + planned items up to the date |

**Bill matching:** any landing transaction (manual, SimpleFIN, CSV) that hits the same account with the same sign, an amount within ±max(3%, $2) and a date within ±4 days of a recurring item's `next_due` marks it paid and advances the due date. **Deviation alerts:** set `deviation_threshold_cents` on an account (PATCH account); the bank-reported `synced_balance_cents` (auto from sync, or set manually via PATCH account for cash) is compared to the ledger balance after every sync and nightly at 07:30.

### Invoicing (clients, invoices, payments, AR)

Invoice `status` stores only the user-set lifecycle (`draft|sent|paid|void`); `subtotal_cents`/`total_cents`/`paid_cents`/`balance_cents`/`overdue` are computed on every read. A fully paid invoice flips to `paid` automatically; removing a payment reopens it. Client records carry a reserved `contact_id` for the future CRM module.

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `GET`/`POST` | `/finance/books/{id}/clients` | read / edit | `{name, email?, phone?, notes?}` |
| `PATCH`/`DELETE` | `/finance/books/{id}/clients/{cid}` | edit | DELETE `409` while the client has invoices (archive instead) |
| `GET` | `/finance/books/{id}/clients/ar` | read | per-client rollup: invoiced/paid/outstanding/overdue cents + counts + last_payment, worst offender first |
| `GET`/`POST` | `/finance/books/{id}/invoices` | read / edit | `{client_id?, issue_date?, due_date, line_items: [{description, qty, unit_cents}], tax_pct?, notes?}`; number auto-assigned from the book's `invoice_prefix` + sequence |
| `GET`/`PATCH`/`DELETE` | `/finance/books/{id}/invoices/{iid}` | read / edit | PATCH takes any create field + `status` |
| `POST` | `/finance/books/{id}/invoices/{iid}/payments` | edit | `{amount_cents, date?, method?, account_id?, category?}` — `account_id` set = log a **linked income transaction** (payee = client name, tx carries `invoice_id`/`client_id`) |
| `DELETE` | `/finance/books/{id}/invoices/{iid}/payments/{pid}` | edit | linked ledger transaction stays — remove it separately if it was a mistake |
| `POST` | `/finance/books/{id}/transactions/{tid}/receipts` | edit | multipart `file` — JPEG/PNG/WebP/AVIF/PDF, 10 MB, ≤10 per transaction; uuid disk names |
| `GET`/`DELETE` | `/finance/books/{id}/transactions/{tid}/receipts/{rid}` | read / edit | binary download / `204` |
| `GET` | `/finance/books/{id}/reports/pnl?year=&period=year\|quarter\|month&quarter=&month=` | read | income statement with per-category breakdown |
| `GET` | `/finance/books/{id}/reports/tax?year=&format=json\|csv` | read | deductible transactions summarized per tax bucket; `csv` = line-level export for the accountant |

Tax flags live on transactions (`deductible: bool`, `tax_category` from the book's `tax_categories` list — edit both via PATCH book / PATCH transaction).

### Sharing

Book audience follows the Assets model. Entry: `{target: <name>|team|household|role:<r>, access: read|contribute|edit, caps?}`. Personal shares are **requests** (target gets an Accept/Decline bell notification; the book is invisible until accepted). Pool books take `contributors` instead (no handshake; `shared_with` is rejected). `hidden_from` (names + `role:<r>`) beats shares. **Contribute caps** `{add: [expense|income], edit_own, see_balances, see_all_tx}` default to expense-submission-only; enforcement is server-side (balance-stripped responses, own-entries transaction filter, sign-gated writes, 403 on reports/planning/invoicing reads without `see_balances`). Specificity: a by-name entry fully overrides group/role entries; an account-level entry overrides the book-level one for that account.

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `PUT` | `/finance/books/{id}/access` | owner (personal) / admin (pool) | `{shared_with?, hidden_from?, contributors?}` — new targets are notified (action `finance_share`); re-sharing preserves prior acceptances |
| `PUT` | `/finance/books/{id}/accounts/{aid}/access` | owner / admin | per-account override entries (no `hidden_from` here) |
| `POST` | `/finance/shares/respond` | recipient | `{notif_id, accept}` — accept adds the viewer to `accepted[]` across book + account entries; decline drops a by-name entry entirely |
| `POST` | `/finance/books/{id}/leave` | share recipient | remove self from a book shared with you |
| `GET` | `/finance/members` · `/finance/roles` | module users | names / role list for the share pickers |

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

### Automation Inbox

Workflow-written reviewable items inside the Automations module (no separate module). Business-scope items live in the `_team` pool (`brain/USERS/_team/Automations/inbox.json`); personal items in `USERS/{name}/Automations/inbox.json`. **Named inboxes** route items by `workflow_key` and carry their own `notify` (pinged on new items) and `reviewers` (may act) lists; unmatched keys land in an auto-created **General** inbox. Retention: 500 items per scope, oldest reviewed trimmed first.

**Workflow side — token auth (`X-Automation-Token`, same token as the assets automation API):**

| Method | Path | Notes |
|--------|------|-------|
| `POST` | `/automations/inbox/items` | `{user: "_team"\|name, workspace, workflow_key, items:[{external_id, title, summary?, url?, fields?}]}` (≤100/batch). Dedup by `(workflow_key, external_id)` — re-posts are skipped. Routes to the claiming inbox; its `notify` members each get ONE batched notification (in-app `open_inbox` action + push deep link `/automations?view=inbox&inbox=<id>`). Returns `{created, skipped, inbox_id}` |
| `GET` | `/automations/inbox/seen?user=&workflow_key=` | `{seen: [external_ids]}` — all known ids for that workflow, so a run can skip re-qualifying listings it already submitted |

**Human side — JWT, `automations` module, workspace-scoped via `X-Workspace`:**

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `GET` | `/automations/inbox` | module users | `{inboxes, items}`; each inbox annotated `_can_act`/`_can_manage` |
| `POST` | `/automations/inbox/items/{id}/status` | admin / inbox reviewer / personal owner | `{status: new\|interested\|passed\|offer_made\|closed, note?}` — records `status_by`/`status_at` |
| `DELETE` | `/automations/inbox/items/{id}` | admin (business) / owner (personal) | `204` |
| `POST` | `/automations/inboxes` | admin (business) / owner (personal) | `{name, notify?, reviewers?, workflows?}` |
| `PATCH` | `/automations/inboxes/{id}` | same | any of name/notify/reviewers/workflows |
| `DELETE` | `/automations/inboxes/{id}` | same | `409` while it still has items |

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
