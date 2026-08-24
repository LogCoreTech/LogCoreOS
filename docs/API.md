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
Public. Returns whether self-registration is open and whether this instance is a public demo.

**Response**
```json
{ "registration_open": true, "demo_mode": false }
```

`demo_mode` mirrors the `DEMO_MODE` env var — the frontend shows a persistent "this is a demo" banner when true. Never true on a personal or managed-hosting instance.

### `POST /auth/register`
Create an account. Requires admin token when registration is closed (except for the very first user).

**Body**
```json
{
  "email": "user@example.com",
  "password": "mypassword",
  "name": "Alice"
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

**Response** `{ "allow_open_registration": false, "enabled_workspaces": ["personal", "business"], "session_minutes": 10080 }`

### `PATCH /auth/admin/settings`
Update runtime admin settings. All fields optional — only send what changes.

**Body** `{ "allow_open_registration": true }` and/or `{ "enabled_workspaces": ["personal"] }` and/or `{ "session_minutes": 43200 }`

`enabled_workspaces` — instance-wide list of workspaces available on this install (subset of `["personal", "business"]`, never empty). Hiding a workspace removes it for **everyone, including admins**: `get_current_user()` intersects each user's `workspaces` with this list. Used for personal-only or business-only deployments.

`session_minutes` (60–129600, default 10080) — a **single instance-wide value**, admin-only, no per-user override. Controls how long every login stays valid (both the JWT `exp` claim and the cookie `max_age`). There used to be a per-user `PATCH /auth/session` self-service endpoint; it was removed in favor of this single admin-controlled setting. Changing it only affects logins from that point forward — already-active sessions are not forcibly invalidated.

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
  "workspaces": ["personal"],
  "contact_id": null
}
```

`workspaces` defaults to `["personal"]` if omitted.

`contact_id` (optional, 2026-08-17): link this new account to an existing household-pool contact (see `GET /contacts/available-for-linking`) instead of lazily auto-creating a fresh self-contact on first `/contacts/me` visit. `400` if the contact doesn't exist or is already `self_of` someone else. Creation-only — no other endpoint retroactively links an existing contact to an account.

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
Delete a user and their Brain folder. **`409`** if the user owns any item already shared with
someone else (an Asset tree, Finance book, Contact, or shared Notes folder/note) — use the
deletion-preview/deletion-execute endpoints below to resolve those first. Users with nothing
shared still delete immediately.

### `GET /auth/admin/users/{user_id}/deletion-preview`
Everything needed to build the delete-review page for this user.

**Response**
```json
{
  "eligible_items": [
    { "module": "assets", "workspace": "personal", "item_id": "...", "item_type": null,
      "label": "Garage", "shared_with": [...], "contributors": [...] }
  ],
  "blast_radius": [
    { "module": "finance", "workspace": "personal", "owner": "Carol", "item_id": "...",
      "label": "Family Budget", "access": "read" }
  ],
  "candidate_users": [ { "id": "...", "name": "Bob", "workspaces": ["personal", "business"] } ]
}
```
`eligible_items` — items this user OWNS that are already shared with someone (the whole tree/book/
folder is one atomic unit; `item_type` is `"note"`/`"folder"`, only meaningful for `notes`). Every
entry here needs an explicit decision before the account can be deleted. `blast_radius` — read-only:
what the user will separately lose access to elsewhere (items owned by others or a pool). `module` is
one of `assets`/`finance`/`contacts`/`notes`.

### `POST /auth/admin/users/{user_id}/deletion-execute`
Resolve every eligible item, then delete the account. Rejects (400) if any eligible item (recomputed
fresh server-side — never trusts the client's set) is missing a decision, or if a `transfer_user`
target doesn't have the item's workspace enabled.

**Body**
```json
{
  "decisions": [
    { "module": "assets", "workspace": "personal", "item_id": "...",
      "action": "transfer_user", "target_user_id": "..." },
    { "module": "finance", "workspace": "personal", "item_id": "...",
      "action": "transfer_pool", "target_user_id": null },
    { "module": "contacts", "workspace": "business", "item_id": "...",
      "action": "delete", "target_user_id": null }
  ]
}
```
`action`: `transfer_user` (needs `target_user_id`) | `transfer_pool` (the item's own workspace's
`_household`/`_team`) | `delete`. Existing `shared_with`/`contributors`/`hidden_from` on a transferred
item are preserved unchanged for a user destination; for a pool destination `shared_with` entries are
converted to equivalent `contributors` entries (pool items never read `shared_with`). Recipients of a
`transfer_user` get one batched in-app notification per delete-run, not one per item. References to
the departing user in every OTHER store are stripped automatically as part of the same call — no
decision needed for that. The account + Brain folder are only deleted after every decision succeeds.

**Response** `{ "ok": true }`

---

## Tasks

### `GET /tasks`
List all tasks for the current user.

**Response** — array of task objects.

### `GET /tasks/top3`
Return the top 3 scored pending tasks.

### `GET /tasks/scored`
Return all pending tasks sorted by score descending. Scoped to the caller's own pending, non-goal tasks — doesn't cover household/team assigned tasks or the All/Done/Overdue filter tabs, so the Tasks page's own "Sort by: Priority" mode instead ports the same formula to a client-side `scoreTask()` (`lib/constants.js`) that can rank whatever's currently on screen.

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
Update the category priority order for one or both pool pseudo-users. Admin only.

**Body** `{ "household"?: ["Family", "Home", "Errands"], "team"?: [...] }` — both keys are optional;
send only the pool(s) you're updating. (Corrected from an earlier `{pool, order}` shape documented
here that never matched the actual route.)

**Response** `{ "ok": true }`

---

## Chat

### `POST /chat`
Send a message to the AI, or resume a paused turn. Returns a streaming response with step trace.

**Body**
```json
{
  "message": "What should I focus on today?",
  "history": [
    { "role": "user", "content": "Hi" },
    { "role": "assistant", "content": "Hello! How can I help?" }
  ],
  "mode": "auto",
  "cross_workspace": false,
  "accept_overage": false,
  "resume": null,
  "chat_id": "b3f1..."
}
```

- `mode`: `"approve"` (default) | `"plan"` | `"auto"` | `"research"`. Approve mode runs reads freely but pauses before any write: the response has `mode: "awaiting_approval"` and `steps` containing `pending_write` entries (`{ type, tool, input, step }`), plus a `run_id`. Plan mode proposes a whole plan before executing (`pending_plan` step, `{ type, summary, actions, step }`). A clarifying question pauses in every mode (`pending_question` step, `{ type, question, header, options, multi_select, step }`, response `mode: "awaiting_answer"`). Research mode adds Tavily web search, read-only.
- `message`: optional — omit when sending `resume` instead (exactly one of the two is required).
- `resume`: `{ run_id, decision?, answer? }` — replays/answers a paused turn instead of sending a new message (2026-08-09). `decision`: `"approve"` (write: replays the *exact* originally-proposed tool call, never re-derived; plan: continues the loop) or `"decline"` (write/plan: the model receives a structured `{"declined": true}` result). `answer`: `string[]`, required when resuming a `pending_question` — becomes the tool result directly. A resumed run_id is consumed immediately server-side, so replaying it twice (e.g. a double-submitted click) is a no-op the second time (`{ "mode": "expired", ... }`).
- `cross_workspace`: when `true` and the user has both workspaces, the AI searches both personal and business Brain paths (results prefixed `personal/` or `business/`). Only available to dual-workspace users. Ignored when resuming — the *original* turn's workspace is used, so a replayed action can't drift to wherever the caller happens to be now.
- `accept_overage`: only relevant when the caller is soft-capped (see **AI Usage** below) and already over their limit — set `true` to proceed anyway. When usage is hard-blocked the response is `{ "response": "...", "steps": [], "mode": "usage_blocked" }` and nothing runs; when soft-blocked and `accept_overage` is not yet `true`, the response is `{ "mode": "usage_confirm_required", ... }` and the frontend re-sends with `accept_overage: true` to continue. Accepting holds for the rest of that user's current cap period.
- `chat_id` (**required**, 2026-08-15): a stable per-conversation id, minted client-side (`crypto.randomUUID()`) the moment a genuinely new conversation starts. Every turn of that conversation — across however many separate `POST /chat` round trips it takes — carries the same `chat_id`, which is what threads the request to one `chat_sessions.json` entry (see **`GET /chat/sessions`** below). The response echoes it back as `{ "chat_id": "...", ... }`. Before the model call, the handler marks that session's `status` `"running"`; on an unhandled exception it's reset to `"idle"` rather than left stuck; on success `notify_user()` fires unconditionally, so a conversation left running in the background (the caller navigated away or closed the app) still produces a notification when it finishes.
- **The user's message is archived immediately, before the model is called (2026-08-17)** — for a fresh (non-resume) turn, the handler writes `history + [the new user message]` to the chat archive right after marking the session `"running"`, *before* `run_agent()` runs. Previously the user's message and the assistant's reply were only ever written together, after the agent call returned — if the call raised or the request was interrupted, the user's own message was never saved at all. The assistant's reply still gets appended in the normal completion write once the run finishes.

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
Delete a saved chat file. Also removes that conversation's `chat_sessions.json` entry (2026-08-15), so a deleted chat's row disappears from the Chats drawer immediately rather than lingering as a dangling filename reference.

**Response** `{ "ok": true }`

### `GET /chat/sessions` (2026-08-15)
List this user's conversations in the active workspace — the real source for the Chats drawer, in place of `/saved`'s plain filename listing. Most-recently-touched first.

**Response** — array of session objects:
```json
{
  "chat_id": "b3f1...",
  "title": "What should I focus on today?",
  "filename": "2026-08-15_09-30-00.md",
  "status": "idle",
  "unread": false,
  "updated_at": "2026-08-15T09:31:02Z",
  "last_message_preview": "Here's what I'd prioritize today..."
}
```
- `status`: `"idle"` | `"running"` | `"awaiting_approval"` | `"awaiting_answer"`.
- `unread`: set `true` when a run finishes or pauses for a conversation that wasn't the one open in the requesting session at the time; cleared via `POST /chat/sessions/{chat_id}/read` or by opening that conversation.
- Capped at 50 most-recent conversations per user per workspace.

### `POST /chat/sessions/{chat_id}/read` (2026-08-15)
Mark one conversation's `unread` flag `false` — called when the user opens it from the Chats drawer.

**Response** `{ "ok": true }`

### `GET /chat/pending/{chat_id}` (2026-08-15)
The live `pending_write`/`pending_question`/`pending_plan` card for one conversation, if it currently has one. The saved `.md` archive only ever stores plain role/content turns — reopening a conversation left mid-approval previously reloaded the assistant's prompt text fine but lost the actual interactive card (and its `run_id`, needed to act on it) entirely. `Chat.jsx` calls this when a session's own `status` (from `GET /chat/sessions`) is `awaiting_approval`/`awaiting_answer`, and re-attaches the result onto the last loaded message.

**Response** — `{ "run_id": "...", "mode": "awaiting_approval" | "awaiting_answer", "steps": [...] }` (the same `steps` shape a live pause response's `steps` field already carries), or `null` if this conversation has no live pending turn (already resolved, or never paused).

### `POST /chat/presence` (2026-08-15)
Tells the server "I'm still looking at this conversation" — `Chat.jsx` calls this on mount/whenever the open conversation changes, and every 20s while the tab is open and visible. `POST /chat`'s completion handler checks this before sending a completion/approval notification and before marking the session unread — both are skipped if the user is still there watching it live. Presence is a single most-recent value per user (not a history) and goes stale on its own after 45s of no pings — there's no explicit "I left" call.

**Body** `{ "chat_id": "..." }`

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

All three endpoints below respect the `X-Workspace` header (2026-08-22 fix — previously
always resolved against the personal folder regardless of the header, so a business-workspace
file, e.g. a chat archive, silently 404'd). `Business/` is rejected as an explicit path segment
on every request regardless of workspace — it's ws_path()'s own business-workspace base folder,
physically nested inside the personal one on disk, not an ordinary personal subfolder.

### `GET /brain/files`
List all `.md` files in the user's brain folder for the active workspace.

### `GET /brain/files/{path}`
Read a brain file. Path is relative to the active workspace's brain folder.

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

Notes support **asset-style sharing**: the response of `GET /notes` includes the viewer's own notes plus **pool** (household/team) and **shared-to-me** notes/folders, each annotated `_owner`/`_access`. Share metadata lives in a sidecar `Notes/_shares.json` (content stays plain `.md`). A share on a folder cascades to its subtree. Every read/write resolves access server-side (`read` < `contribute` (edit content) < `edit` (move/delete/reshare)).

### `GET /notes`
List all notes and folders visible to the current user (own + pool + shared), annotated
`_owner`/`_access`/`archived`. Archived items are omitted by default — pass `?include_archived=true`
to include them too.

### `POST /notes/archive`
Archive or unarchive a note/folder (edit-level access required — same gate as delete). Archiving is
per-node, not cascaded (mirrors Assets' archive rule): archiving a folder does not archive its
contents. Purely organizational — has no effect on delete permissions.

**Body** `{ "path": "Projects/old-plan", "archived": true }`

**Response** `{ "ok": true }`

### `GET /notes/file/{path}`
Read a note file. Resolves the note's store (own/pool/shared) and requires read access.

### Sharing

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `PUT` | `/notes/access` | owner / pool admin | `{path, shared_with?, hidden_from?, contributors?}` — new targets notified (action `notes_share`); pool paths take `contributors` (no handshake), personal take `shared_with` (accept/decline) |
| `POST` | `/notes/shares/respond` | recipient | `{notif_id, accept}` |
| `POST` | `/notes/leave` | recipient | `{path}` — remove self from a note shared with you |
| `GET` | `/notes/members` · `/notes/roles` | module users | share pickers |

`POST /notes/file` and `/notes/folder` accept an optional `pool: true` (admin) to create in the household/team pool store.

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

**Agent tools**: `list_notes`/`read_note`/`search_brain` (read; `search_brain` also walks pool/shared notes, not just the caller's own) + `create_note`/`update_note`/`delete_note`/`move_note`/`create_note_folder` (approval-gated). All resolve through the same sharing-aware access check the HTTP API uses (`read` < `contribute` < `edit`) — the agent can see and use anything shared with the caller, not just their own notes, and returns a plain-language error rather than silently failing if the caller's access level is too low for the requested action. `read_note`/`update_note`/`delete_note`/`move_note` accept an optional `owner` hint (from a prior `list_notes`/`search_brain` result's `_owner` field) to disambiguate when the same relative path could exist in more than one store the caller can reach.

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
| `GET` | `/assets/by-contact/{contact_id}` | module users | viewer-visible assets referencing this contact in a **`contact`-type template field** (field type stores a CRM contact id; renders a ContactPicker in the editor and a jump link in AssetView). Feeds the contact References section |
| `POST` | `/assets` | module users | `{template_id\|template, name, parent_id?, fields?, custom_field_defs?, notes?, owner:"me"\|"pool"}`; **`template_id`/`template` are both optional (2026-08-17)** — omit both for a blank asset (`template`/`template_id` come back `null`); `pool` needs admin/`pool_edit`. `parent_id` set → child created in the **parent's store** (requires edit access) inheriting its `shared_with`+`hidden_from` (the "group" mechanic). Asset responses embed the resolved template as `_template` (`{}` for a blank asset — never `null`; `null` specifically means a stale template reference that used to exist and was deleted). When the record is created outside the caller's own store, the response carries `_owner` (`team`/`household`/owner name) + `_access: "edit"` like list/find responses |
| — | — | — | **`fields` on a blank asset** (no `template_id`/`template` at all) is freeform by default (2026-08-17) — any `{label: value}` pairs are accepted directly (label trimmed/capped to 60 chars, value to 2000, capped at 40 fields), UNLESS the key matches an entry in **`custom_field_defs`** (2026-08-18), in which case it gets the same typed `_validate_value()` check a templated field would (`text\|number\|date\|boolean\|select\|contact`, same shape/validation as a real Template's own `fields: [{key,label,type,options?}]`, via `_validate_field_defs()`). An undefined key still falls back to freeform. A real template with an empty `fields` array (e.g. the seeded Folder template) is NOT treated as blank — it still rejects unknown keys as `400 Unknown field`, and `custom_field_defs` has no effect on it. |
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
| `POST` | `/assets/{id}/attach-template` | edit access | `{template_id}` (2026-08-18) — "Save as template" second half: retroactively attaches a real Template to a currently-blank asset (frontend creates the Template first via a plain `POST /assets/templates` call from the asset's own `custom_field_defs`, then calls this). `400` if the asset already has a template. Self-service, unlike `/convert` above — this never touches sharing/pool membership, just which template the caller's own asset points at. Clears `custom_field_defs` and re-validates existing field values against the template's real defs (should pass unchanged, checked anyway) |
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
| `POST` | `/finance/books/{id}/transactions` | edit | `{date, amount_cents, account_id, category?, payee?, payee_contact_id?, asset_id?, notes?, deductible?, tax_category?}`; category must exist on the book or be `""`. `payee_contact_id` links the payee to a CRM Contact (bank/CSV imports auto-suggest one); `asset_id` links the transaction to an Asset (picker in the tx modal when the assets module is on) |
| `PATCH`/`DELETE` | `/finance/books/{id}/transactions/{tid}` | edit | date edits across a year boundary move the record between year shards transparently |
| `GET` | `/finance/assets/{asset_id}/transactions` | module users | transactions tagged with this asset across **every book the viewer can see** (contribute-capped viewers without `see_all_tx` get own entries only); each carries `book_id`/`book_name`; feeds the AssetView "Finance activity" section + deal rollups |
| `GET` | `/finance/books/{id}/reports/monthly?month=YYYY-MM` | read | income/expense/net + per-category breakdown, computed on read |
| `GET` | `/finance/networth` | module users | per-book totals + a total **grouped by currency** (`totals_by_currency: {"USD": ..., "EUR": ...}`) across all visible books in the workspace — never blended across currencies |

### Bank sync (SimpleFIN — admin-managed) + CSV import

Bank connections use SimpleFIN Bridge **read-only** tokens. Members never enter tokens: they *request* a connection (admins get a bell/push that deep-links straight to that member's page), an admin claims the user's setup token from that member's own page under Settings → Admin Settings → Users & Roles, then the member maps connected bank accounts onto their own book accounts from **Finance → 🏦 Bank**. The access URL lives at `brain/USERS/{name}/Finance/simplefin.json` and is only ever output by the admin reveal endpoint. Sync runs 2 min after boot + every 12 h; imported transactions land uncategorized (`category: ""`) unless a learned payee rule matches.

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `POST` | `/finance/simplefin/request` | module users | notify all admins (rate 3/hour); notification action carries `user_id` so the admin lands on the requesting member's page |
| `GET` | `/finance/simplefin/status` | module users | own sanitized status — never includes the access URL |
| `GET` | `/finance/simplefin/accounts` | module users | live list of connected bank accounts (for the mapping UI) |
| `PUT` | `/finance/simplefin/mapping` | module users | `{entries: [{simplefin_account_id, bank_name?, account_name?, target: {store: self\|household\|team, workspace, book_id, account_id}, enabled}]}` — pool targets **admin-only** |
| `GET` | `/finance/simplefin/connections` | **admin** | per-user connection status, used to populate each user's own Bank Connection section |
| `GET` | `/finance/simplefin/pool-summary?pool=household\|team` | **admin** | read-only, derived from every user's `account_map`: which members have accounts mapped into that pool's books (`[{user_id, name, mapped_accounts}]`). Distinct from — and unaffected by — the pool's own connection below; a pool can receive money both ways at once |
| `POST` | `/finance/simplefin/claim` | **admin** | `{user_id, setup_token}` → claims + stores the access URL for that user; notifies them (rate 5/hour) |
| `POST` | `/finance/simplefin/reveal` | **admin** | `{user_id}` → the stored access URL (rate 3/hour — the only endpoint that outputs it) |
| `DELETE` | `/finance/simplefin/{user_id}` | **admin** | disconnect (deletes the stored token; imported data stays) |
| `POST` | `/finance/simplefin/sync` | **admin** | `{user_id}` → run a sync now; returns `{created, skipped, errors?}` |

**Pool-owned connections** (added 2026-08-12): a joint/family bank account connected directly to the
`_household`/`_team` pseudo-user itself, independent of any one member's own SimpleFIN connection —
for accounts that genuinely aren't "one person's." Admin-only end to end (no request/claim handshake —
an admin can connect it proactively at any time), and mapping targets are always that same pool's own
books (`target.store` must equal `pool`). `_household`/`_team` are real per-pool folders like any other
user's, so this reuses every function above unchanged — just resolves `pool` to that pseudo-user name
first. Included in the same nightly/boot sync sweep as user connections.

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `GET` | `/finance/simplefin/pool/{pool}/status` | **admin** | sanitized status for the pool's own connection (`pool`: `household`\|`team`) |
| `GET` | `/finance/simplefin/pool/{pool}/accounts` | **admin** | live bank accounts on the pool's connection, for its mapping UI |
| `PUT` | `/finance/simplefin/pool/{pool}/mapping` | **admin** | same entry shape as the member mapping endpoint above |
| `POST` | `/finance/simplefin/pool/{pool}/claim` | **admin** | `{setup_token}` → claims + stores the access URL for the pool (rate 5/hour) |
| `POST` | `/finance/simplefin/pool/{pool}/reveal` | **admin** | the stored access URL (rate 3/hour) |
| `DELETE` | `/finance/simplefin/pool/{pool}` | **admin** | disconnect |
| `POST` | `/finance/simplefin/pool/{pool}/sync` | **admin** | run a sync now |

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
| `GET`/`POST` | `/finance/books/{id}/invoices` | read / edit | `{client_id?, deal_id?, issue_date?, due_date, line_items: [{description, qty, unit_cents}], tax_pct?, notes?}`; number auto-assigned from the book's `invoice_prefix` + sequence. `deal_id` links the invoice to a CRM deal (a deal can bill many invoices) |
| `GET` | `/finance/deals/{deal_id}/invoices` | module users | invoices billing this deal across **every book the viewer can see** (contribute books without `see_balances` skipped); each carries `book_id`/`book_name`. Feeds the deal panel's invoice list + Job P&L |
| `GET`/`PATCH`/`DELETE` | `/finance/books/{id}/invoices/{iid}` | read / edit | PATCH takes any create field + `status` |
| `POST` | `/finance/books/{id}/invoices/{iid}/payments` | edit | `{amount_cents, date?, method?, account_id?, category?}` — `account_id` set = log a **linked income transaction** (payee = client name; tx carries `invoice_id`/`client_id`/`deal_id`, and auto-links the deal's asset when it has exactly one). The frontend opens the created transaction immediately so it can be finished (category/asset/notes) |
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

### Transfers

Router `finance_transfers.py`, mounted at the same `/api/v1/finance` prefix. A Transfer is **not** a new stored entity — it's two ordinary transactions (one leg per book) linked by a shared `transfer_pair_id`, each carrying denormalized peer info (`transfer_peer_book_id`, `transfer_peer_book_name`, `transfer_peer_account_id`, `transfer_peer_account_name`, `transfer_peer_workspace`) so the frontend never needs a separate lookup to render or edit one. Both legs are excluded from `reports/monthly`, `reports/pnl`, and `budgets/status` sums. Category is always `""` (uncategorized). Unlike every other finance endpoint, the two legs' workspaces are **not** taken from the ambient `X-Workspace` header — each is passed explicitly in the body, since the two books can legitimately be in different workspaces.

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `POST` | `/finance/transfers` | edit on **both** books | `{from_book_id, from_workspace, from_account_id, to_book_id, to_workspace, to_account_id, amount_cents, date, notes?}` — rejects mismatched currencies and a workspace the caller isn't entitled to; same book/account for both sides is rejected. Creates both legs; best-effort deletes the first leg if the second fails |
| `PATCH` | `/finance/transfers/{transfer_pair_id}` | edit on both books | body carries both legs' `book_id`/`workspace` explicitly (the frontend always has these from the peer fields); updates amount/date/notes on both legs together — amount sign is flipped automatically for the "from" leg. Does not support moving a transfer to different books/accounts — delete and recreate instead |
| `DELETE` | `/finance/transfers/{transfer_pair_id}?from_book_id=&from_workspace=&to_book_id=&to_workspace=` | edit on both books | removes both legs together |

**Guard on the ordinary single-tx endpoints:** `PATCH`/`DELETE /finance/books/{id}/transactions/{tid}` now `409` if the target transaction has `transfer_pair_id` set — a transfer's legs can only be edited/deleted as a pair, through the endpoints above. `finance_planning_service.on_transactions_added()` (bill-matching/budget-alert sweep) is deliberately not invoked for transfer legs — `match_bill()`'s matching is category-blind and could otherwise false-match a transfer leg to an unrelated recurring bill.

Note: "same book/account for both sides is rejected" above means only the exact same account is rejected — a transfer between two accounts **within the same book** (e.g. Checking → Savings) has always been supported; nothing changed here (2026-08-15).

### Preferences

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `GET`/`PUT` | `/finance/prefs` | module users | `{last_book_id: {personal: "...", business: "..."}}`, workspace-keyed (2026-08-15). `Finance.jsx` reads it on mount only when no `?book=` query param is present, and writes it whenever the user actively switches books (not on the initial default-book resolution, to avoid a stale-book ping-pong) |

---

## Contacts (CRM)

Router mounted at `/api/v1/contacts`. Requires the `contacts` module (both workspaces, `X-Workspace`-scoped; **disabled for `guest`** by default) — **except `/contacts/me`, gated by login only** (see below). The **Contact** is the canonical person/company **and, since the Profile/Contacts merge, every user's own Profile too**; Finance payees (`payee_contact_id`) and invoice clients (`contact_id`) link to it. Storage: `ws_path/Contacts/{contacts,interactions,deals,pipeline}.json` + `Contacts/photos/{contact_id}.{ext}` for uploaded photos; admin custom-field defs at `_system/contact_fields.json`; pool contacts in `_household`/`_team`. Contact responses are annotated `_owner`/`_access`/`_pinned` (self-contact only, own view only — `_owner` is omitted on your own self-contact's own view, present as normal for anyone else viewing it) , `_online: bool`, and `_last_seen: str | None` (self-contacts only, wired up 2026-08-17 — reads `presence_service.is_online()`/`last_seen_iso()`; never present on an ordinary contact, and only ever computed for a record the caller already has resolved access to, so there's no separate way to look up an arbitrary user's presence). `_last_seen` is the raw last-ping ISO timestamp (or `null` if never pinged) — the frontend formats it into a coarse relative label (minutes for the first hour, hours up to a day, days uncapped after that). Sharing mirrors Finance/Assets (read/contribute/edit; **contribute = log interactions + create/advance deals only**; personal = accept handshake, pool = contributors; `hidden_from` beats shares) — **except a fixed set of "private" fields (health, finances, AI preferences, daily routine) which are never shareable, regardless of access level, and a self-contact can never be shared at `edit` — only `read`/`contribute`, so nobody but its owner can ever change it**. **A new contact defaults into its workspace's pool** (2026-08-17) — visible to the whole household/team unless "make personal" is chosen at creation; pool-contact creation is no longer admin-only, and the creator gets `edit` on what they made. A `cross_workspace: bool` field (default `false`) makes a contact resolvable from the opposite workspace too, as the same record — off by default for an ordinary contact, forced permanently `true` for a self-contact.

### Self-contact (Profile)

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `GET` | `/contacts/me` | **login only, no module gate** | the caller's own self-contact (`self_of` = their name), auto-created on first access. **Physically stored in the household pool** (2026-08-17, moved out of the caller's own store — see `docs/AGENTS.md`), resolvable/editable from either workspace — one record, not per-workspace |
| `PATCH` | `/contacts/me` | **login only, no module gate** | same body shape as `PATCH /contacts/{id}` below |
| `POST`/`DELETE` | `/contacts/{id}/affiliations/{other_id}` | module users, edit on **both** contacts | general bidirectional Contact↔Contact link (family, company↔person, etc.) — a dedicated mutation, never part of the general PATCH; cross-owner linking (edit on only one side) is rejected |
| `POST` | `/contacts/{id}/photo` | edit | multipart `file` — JPEG/PNG/WebP/AVIF, 5 MB cap. Any contact with edit access, not just self-contacts. Replaces any existing photo |
| `GET` | `/contacts/{id}/photo` | any access | binary response; `404` if none uploaded |
| `DELETE` | `/contacts/{id}/photo` | edit | `204` |

`ContactCreate`/`ContactUpdate` also accept the merged-in profile fields: **basic** (shareable) — `pronouns, gender ("male"|"female"), city, state, country, occupation, marital_status, pets, life_mission, core_values, key_constraints`, `priority_order: {"personal": [...], "business": [...]}` (the one workspace-keyed field), `cross_workspace: bool` (see above; forced `true`, un-toggleable, on a self-contact), and `career_history` (resume-style list, see below); **private** (never shareable, stripped for any viewer who isn't the record's own owner) — `wake_weekday, wake_weekend, bedtime, work_start, work_end, height_cm, height_unit ("ftin"|"cm"), weight_kg, weight_unit ("lbs"|"kg"), blood_type, conditions, medications, diet, exercise, income_range, budget_style, communication_style, tone, response_language, topics_to_emphasize, topics_to_avoid`. `self_of` and `affiliated_contact_ids` are never settable through these models — only via `/contacts/me`'s auto-creation, the create-user `contact_id` linking flow, and the dedicated affiliation endpoints respectively.

**`core_values`** — `list[str]` (2026-08-18, was a single comma-separated string before this — pill entries now, like `tags`), trimmed/deduped/capped at 30 entries of 60 chars each. Also accepts a raw comma-separated string on input (split the same way the one-time `m014` migration converts existing data) since the AI's `update_contact`/`update_profile` tools bypass this Pydantic model's type entirely, calling the service layer directly with a raw dict.

**`career_history`** — a resume-style list, each entry `{id, title, company_id, industry, education, years_experience, skills, start_date, end_date, archived}`. `education` must be one of a fixed list (`EDUCATION_LEVELS` in `contacts_service.py`: Junior High, High School, Some College, Trade/Vocational School, Associate's/Bachelor's/Master's Degree, Doctorate, Other) — anything else 400s. `company_id` links to a company-type Contact. Not a separate resource: send the whole array on `PATCH`; the client can mark the current entry `archived: true` + set `end_date` and append a fresh entry to "start a new role," **or (2026-08-18) append/edit a past entry directly with its own explicit `start_date`/`end_date`** — the backend validates each entry independently and has never enforced "exactly one current entry"; the frontend's own array order doesn't matter either, since both the editor and the read view sort past entries by `start_date` descending for display. Superseded the old flat `employer`/`industry`/`education`/`years_experience`/`skills` fields.

**`hidden_sections`** — `list[str]` (2026-08-18, `ContactUpdate` only — not settable at create time), a subset of six section keys (`values_principles`, `family`, `career`, `address`, `personal`, `priorities`; unknown key → `400`). Self-contact-only in practice (validated generically, but only meaningful when `self_of` is set): each hides its mapped field set from every non-owner viewer, the same way `annotate()`/`find_contact()` already strip the fixed `_PRIVATE_FIELDS` set — except this one is per-contact and owner-chosen rather than fixed and universal. **Settable only by the contact's own owner** — `update_contact()` silently strips `hidden_sections` from any incoming PATCH where the acting viewer isn't `self_of`, same guard that already protects `_PRIVATE_FIELDS` from third-party injection. The record's own owner always sees every section regardless of what's hidden from others.

**`type`** is `"person"` or `"company"` (`CONTACT_TYPES`). It's stored and validated the same for both, but the frontend (`ContactModal.jsx`/`ContactDetail.jsx`) shows different sections by type: person gets the basic/private personal fields above plus `career_history`; company gets `locations`/`hours` below instead, and its "Family" section is relabeled "Affiliated People" (the `affiliated_contact_ids` mechanism itself is identical for both). A self-contact (`self_of` set) is guarded server-side to stay `"person"` — a `PATCH` that tries to flip it to `"company"` is rejected.

**`locations`** — a list of `{id, label, address}`, capped at 20; entries that are entirely blank are dropped on save. **`hours`** — always exactly 7 entries in day order (Mon–Sun), each `{day, open, close, closed}`; missing days default to closed. Both fields exist on every contact (empty list/default-closed week for a person) but are only shown in the UI for `type: "company"`.

**`phones`** is a list of `{country_code, number, extension}` (digits-only; `number` ≤10 digits, `country_code` ≤3, `extension` ≤6) — a plain string is still accepted for backward compat (legacy data, CSV import, automation) and gets wrapped. **`emails`** now validates format (basic regex) — an invalid address 400s the whole request instead of silently saving.

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `GET` | `/contacts?include_archived=` | module users | own + pool + shared-to-me contacts, PLUS anyone's `cross_workspace: true` contacts reachable from the opposite workspace (2026-08-17 — see `docs/AGENTS.md`); the viewer's own self-contact is always annotated `_pinned: true` (ordering/pinning-to-the-top is a frontend concern, `Contacts.jsx` finds it by `self_of` — the backend doesn't guarantee any particular list position for it) |
| `POST` | `/contacts` | module users | `{type, name, emails?, phones?, address?, tags?, birthday?, status?, notes?, custom?, cross_workspace?, pool?}`; `pool` **defaults `true`** (2026-08-17) — a new contact is pool-shared unless explicitly set `false` ("make personal"). No longer admin-gated — any contacts-module user may create directly in the pool, and gets `edit` on their own creation |
| `GET` | `/contacts/available-for-linking` | **admin** | household-pool contacts with no `self_of` set — candidates for the create-user "link to an existing contact" picker (2026-08-17). Deliberately workspace-independent (always reads the household pool, regardless of the admin's own active tab) |
| `GET`/`PATCH`/`DELETE` | `/contacts/{id}` | per access | PATCH needs edit; DELETE cascades interactions+deals (pool DELETE admin-only) |
| `POST` | `/contacts/{id}/archive` · `/unarchive` | edit | |
| `POST` | `/contacts/{id}/convert` | edit | moves a personal contact into the active workspace's pool (2026-08-17) — self-service, mirrors `transfer_ownership()`; `400` if it's already a pool contact. Returns the full annotated contact (not `{"ok": true}` — the frontend's save flow expects a real record back) |
| `POST` | `/contacts/convert-bulk` | module users | `{contact_ids?: string[]}` (2026-08-17) — bulk version of the above, scoped to the caller's own personal, non-self contacts; omitting `contact_ids` converts everything eligible. Skips (doesn't fail) any id that's already a pool contact or not owned by the caller. Returns `{converted, skipped}` |
| `GET`/`POST` | `/contacts/{id}/interactions` | read / contribute | `{type: call\|email\|meeting\|text\|note, summary, date?, follow_up?}` |
| `PATCH`/`DELETE` | `/contacts/{id}/interactions/{iid}` | contribute / edit | |
| `GET`/`POST` | `/contacts/{id}/deals` | read / contribute | `{title, value_cents, stage?, expected_close?, follow_up?, notes?}`; stage must exist in the pipeline. Deals carry `linked_asset_ids` + a reserved `invoice_id` (written back by the deal→invoice prefill flow) |
| `PATCH`/`DELETE` | `/contacts/{id}/deals/{did}` | contribute / edit | |
| `POST`/`DELETE` | `/contacts/{id}/deals/{did}/assets[/{aid}]` | contribute | link/unlink an existing Asset to the deal (`{asset_id}` body on POST, idempotent). The asset must resolve via `assets_service.find_asset` for the caller — read access on the asset is enough; the gated write is the deal mutation. On a Won deal, 🧾 deep-links `/finance?view=invoices&client_contact=&amount=&title=&deal_id=` → prefilled InvoiceModal (user picks the book and confirms; the created invoice stores `deal_id`) |
| `GET` | `/contacts/deals/{deal_id}` | module users | deal lookup by id alone (for Finance surfaces holding only a deal_id) — access inherits from the parent contact; response carries `_access`/`_contact_id`/`_contact_name` |
| `GET`/`PUT` | `/contacts/pipeline` | module users | `{stages:[...]}` per-store deal pipeline (default Lead→Contacted→Proposal→Negotiation→Won→Lost) |
| `GET` | `/contacts/fields` · `PUT` (admin) | module users / admin | instance-level custom field definitions; each carries `applies_to: ['person','company']` (default both, 2026-08-15) — `ContactModal.jsx`/`ContactDetail.jsx` filter their render loop by `contact.type` client-side. Authored via Settings → Admin Settings → Contact Fields (`ContactFields.jsx`), the first UI ever built for this endpoint — previously only `GET` had a frontend caller |
| `GET` | `/contacts/{id}/finance` | module users | money references for this contact, **scoped to the viewer's finance access**: payee spend/receive totals, `invoices` list (via clients with this `contact_id`, book-labeled, see_balances-gated), `invoices_total_cents`/`outstanding_cents`, and per-deal Job P&L `deals: [{deal_id, title, invoiced_cents, collected_cents, expenses_cents, net_cents}]` (expenses from the deal's linked assets) |
| `PUT` | `/contacts/{id}/access` | owner / pool admin | `{shared_with?, hidden_from?, contributors?}` — new targets notified (action `contacts_share`) |
| `POST` | `/contacts/shares/respond` · `/contacts/{id}/leave` | recipient | accept/decline · leave a shared contact |
| `GET` | `/contacts/members` · `/contacts/roles` | module users | share pickers |
| `POST` | `/contacts/import/csv` · `/import/csv/commit` | module users | preview + column-mapped import (dedup on name/email) |
| `GET` | `/contacts/export/csv` | module users | CSV of visible contacts |

**Automation API** (`X-Automation-Token`, rate 30/min — **write-focused, no bulk export**):

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/contacts/automation/lookup?user=&workspace=&email=&name=` | single-contact dedup lookup → `{found, contact_id}`. Deliberately NOT a list endpoint |
| `POST` | `/contacts/automation/contacts` | create/update by name/email match; `{user, workspace, name, type?, emails?, phones?, tags?, notes?}` |
| `POST` | `/contacts/automation/interactions` · `/deals` | append an interaction / deal to a contact |

**Agent tools**: `list_contacts`/`get_contact` (read) + `create_contact`/`update_contact`/`log_interaction`/`create_deal` (approval-gated; create searches for a match first to avoid duplicates).

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
Send a test push notification to the current user. As of 2026-08-15 the failure cases are distinguishable instead of a collapsed generic error: `400` "No push subscription on file — enable push notifications in Settings first" when the caller has never subscribed, `502` "...push service rejected or failed the send" when a subscription exists but the actual send failed (e.g. `VAPID_SUBJECT` still the default placeholder, an expired subscription, or a network error to the push endpoint).

---

## Automations (n8n)

Router mounted at `/api/v1/automations`. Requires the `automations` module to be enabled (or `automations_business` for business-scope workflows).

### Admin — n8n Config

#### `GET /automations/n8n/status`
Get n8n connection status and workflow count. Admin only.

#### `POST /automations/n8n/config`
Save n8n URL and API key. Admin only. Triggers a container reconcile: attaching an **external** n8n (URL not the bundled `n8n:5678`) stops the bundled `logcore-n8n`; `force_on: true` keeps the bundled container running even with no workflows. Otherwise the bundled container runs only while ≥1 workflow is stored (started on first import, stopped on last delete + boot reconcile).

**Body** `{ "url": "http://logcore-n8n:5678", "api_key": "n8n_api_...", "force_on": false }`

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

Role names are stored strip+lowercased (`"Cleaner"` → `"cleaner"`) and every endpoint below
normalizes its own `role_name` input the same way before doing a lookup, so a differently-cased or
padded name still resolves correctly (fixed 2026-08-12 — see `docs/MEMORY.md`).

### `GET /auth/admin/features`
Get all feature roles and, for each, whether every module is enabled (`true`) or disabled (`false`) —
not just a disabled-list.

**Response** `{ "profile": "personal", "roles": { "member": { "dashboard": true, ... }, "cleaner": { "dashboard": true, "finance": false, ... } } }`

### `POST /auth/admin/features/roles`
Create a new custom feature role. `"member"`/`"guest"`/`"admin"` are reserved names. Modules omitted
from `modules` default to enabled (`true`).

**Body** `{ "name": "cleaner", "modules": { "finance": false, "contacts": false } }`

**Response** `{ "name": "cleaner", "modules": { "dashboard": true, ..., "finance": false, "contacts": false } }` — the full per-module map as stored, including defaulted-`true` keys.

### `PATCH /auth/admin/features/roles/{role_name}`
Replace a feature role's full per-module map (not a partial patch — omitted modules reset to `true`).

**Body** `{ "modules": { "chat": false } }`

### `GET /auth/admin/features/roles/{role_name}/users`
Which users currently have this role assigned — meant to back a real delete-confirmation UI instead of
a generic warning (added 2026-08-12).

**Response** `{ "users": ["Bob Worker"] }`

### `DELETE /auth/admin/features/roles/{role_name}`
Delete a custom feature role. `"member"`/`"guest"` cannot be deleted. Any user currently assigned this
role falls back to `"member"` — check the endpoint above first if you want to warn about that.

### `PATCH /auth/admin/features/users/{user_id}/role`
Assign a feature role to a user. `feature_role` must be `"member"` or an existing custom role name
(`"guest"` is also always valid as the default, even before any role exists). Admins cannot change their
own feature role this way (400).

**Body** `{ "feature_role": "cleaner" }`

---

## Help

Router mounted at `/api/v1/help`. Auth required but **no module gate** (like Settings) — every
signed-in user can read it. The authored content lives in `app/backend/content/help.json` (a single
source read by the Help page, the module-page ⓘ buttons, and the AI's `get_help` tool).

### `GET /help/content`
Full authored guide: `{ sections, faq, support, whats_new }`. Each section is
`{ id, icon, title, blurb, howto[], tips[], modules[], admin_only? }`. `modules[]` powers the "only
my modules" filter; `admin_only` sections are hidden from non-admins client-side.

### `GET /help/whats-new`
Banner state for the current session: `{ version, until, highlights, date }` after an update, or
`{ version: null }` once the window (`WHATS_NEW_DAYS`, default 5) has passed or nothing was announced.

### `GET /help/onboarding`
The current user's first-run checklist state: `{ dismissed, done: [step_ids] }`.

### `PUT /help/onboarding`
Merge-update the checklist. Body `{ dismissed?: bool, done?: [step_id] }` — `done` is unioned into
the existing list (de-duplicated, capped).

**AI integration:** the chat agent has a read-only `get_help` tool (`{ section? }` → the guide as
Markdown with `/help#<id>` anchors), in the `_READ_TOOLS`/`_RESEARCH_TOOLS` allowlists so it runs in
every mode. The chat system prompt also injects a compact capability index of the user's enabled
modules so the AI can point them to the right one.

---

## AI Usage

Router mounted at `/api/v1/ai-usage`. Meters and caps AI spend across the 3 real AI call sites (chat,
save-memory, custom AI-powered suggestions). Usage is stored per user per day in
`brain/_system/ai_usage.json` — operational metadata, never part of a user's portable Brain folder.
Daily/weekly/monthly totals are always derived on read from the day buckets. **Automation (n8n) AI
usage is not tracked** — n8n workflow nodes that call an AI provider directly (using their own
credential) never touch this backend; see `docs/MEMORY.md` Key Decisions Log (2026-07-30).

A cap check sums a user's **personal + business usage combined** (one human, one budget), even
though display responses break the two apart. `mode` is `"off"` (unlimited, the default for every
user) | `"soft"` | `"hard"`. `period` is `"daily"` | `"weekly"` (ISO Monday–Sunday) | `"monthly"`.
Message/token limits are a global default with an optional per-user override; `null` means
unlimited for that metric.

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `GET` | `/ai-usage/overview?month=YYYY-MM` | admin | Instance totals + personal/business breakdown for the given calendar month (default: current), plus `available_months` seen in the data |
| `GET` | `/ai-usage/users?month=YYYY-MM` | admin | Per-user rows: the picked month's personal/business messages+tokens (for comparability), plus each user's own **live** period/mode/effective limits/status (`ok`\|`warn`\|`over`\|`off`) — these two are independent windows |
| `GET` | `/ai-usage/defaults` | admin | `{ period, message_limit, token_limit, warn_pct }` |
| `PATCH` | `/ai-usage/defaults` | admin | Any subset of the same fields — only send what changes |
| `PATCH` | `/ai-usage/users/{user_id}/limits` | admin | `{ period?, mode?, message_limit?, token_limit? }` — only send what changes |
| `GET` | `/ai-usage/me` | any authenticated user | `{ mode, period, message_limit, token_limit, used_messages, used_tokens, pct }` — self-service summary powering the Chat toolbar's usage indicator; `pct` is the higher of the message-limit and token-limit ratios, or `null` when `mode` is `"off"` |

**Enforcement**: hard mode blocks chat, save-memory, and suggestions outright once over the limit for
the current period. Soft mode only interactively gates `POST /chat` (see `accept_overage` above) —
save-memory and suggestion runs have no confirm UI, so they proceed once a user has accepted the
overage for that period (or were never asked, if under the limit). Warn (default 80% of the limit)
and over notifications fire once per cap period via the existing notification-inbox/push mechanism;
admins are also notified when a user hits a **hard** cap.

---

## Custom Dashboards

Router mounted at `/api/v1/dashboards`. Requires the existing `dashboard` module (both workspaces,
`X-Workspace`-scoped — no new `require_module` registry entry). A dashboard is a **standalone,
unlimited, user-created object** — like Notes/Assets, never owned by a Contact/Asset record —
storing an ordered list of typed **blocks** on a freeform grid. Storage: `ws_path/Dashboards/dashboards.json`;
pool dashboards live under `_household`/`_team` the same way pool Assets/Finance/Contacts do.

Sharing mirrors Assets/Notes/Contacts exactly: `shared_with` (personal, accept-handshake,
read/contribute/edit), `hidden_from` (beats shares), `contributors` (pool, no handshake). Access
resolution goes through `dashboards_service.resolve_access()`/`find_dashboard()`.

**Cross-workspace visibility `cross_workspace`** (2026-08-18, default `false`): a dashboard normally
only appears in the workspace it was created in — `find_dashboard()`/`list_visible_dashboards()` only
ever check one workspace's stores. Setting `cross_workspace: true` (via `PATCH /dashboards/{id}`, edit
access required — a stronger gate than the `contribute` tier the rest of that endpoint's fields use,
matching how sharing/visibility changes elsewhere in this module are edit-gated) makes that one record
additionally reachable from the opposite workspace too, via a second own/pool/shared pass against the
opposite workspace's stores, each leg filtered to `cross_workspace: true`. There is still exactly one
record in one file — `find_dashboard()` returns `store`/`store_workspace` pointing at wherever it
actually lives (which may be the *opposite* workspace from the one the caller is viewing), and every
write (`PATCH`, access changes, block edits) is redirected there, never duplicated. Mirrors
`contacts_service`'s `cross_workspace`/`effective_workspace()` mechanism, with one deliberate deviation:
`resolve_access()` for an opposite-workspace hit is called with the record's own *native* workspace, not
the viewer's ambient one, so a stored "team"/"household" pool-contributor grant keeps meaning what it
meant when it was written. `resolve_default_dashboard_id()` also folds in the viewer's own
`cross_workspace: true` dashboards from the opposite workspace, so a user whose only dashboard lives in
personal but is flagged cross-workspace still gets it as their business-tab default instead of an empty
state.

**Last-opened restore** (2026-08-18, frontend-only, no new endpoint): `Dashboard.jsx` remembers the last
opened dashboard per workspace in `localStorage` (`lc_dashboard_last_id_{workspace}`) and reopens it on
the module's next boot **if within 30 minutes** of when it was last viewed — otherwise falls back to the
normal resolved default. Same pattern Chat.jsx already uses for its own "last opened conversation"
restore, with an added expiry window Chat's version doesn't need.

**Security model**: every block re-resolves the *current viewer's* own access to whatever it points
at, through that module's own existing gate — a dashboard is a read-through view, never an access
bypass. The one deliberate exception is the owner-only `share_underlying_data` toggle (default
`false`): when on, a shared viewer sees every block rendered *as the dashboard owner* would see it
(even past admin-only block gating), but never more than the owner can independently see — if the
owner's own access is revoked, the block locks for every viewer too. Implemented as a single
two-pass function in `services/dashboard_blocks/render.py`, not per-block-type special-casing.

**Floor-of-one delete protection**: if a user owns exactly one dashboard in a workspace, deleting it
is rejected (`409`) and it's automatically their default for that workspace — computed at read/delete
time, no stored "protected" flag.

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `GET` | `/dashboards` | module users | Own + pool + shared-to-viewer dashboards, **plus** any of those marked `cross_workspace: true` reachable from the opposite workspace too (annotated `_owner`/`_access`), plus the resolved `default_id` for the active workspace |
| `POST` | `/dashboards` | module users | `{name, icon?, pool?}` — `pool:true` = admin only, creates in the workspace pool (always stored at the `personal` ws_path base regardless of ambient workspace, same convention every pool read already assumed — a `_team` pool dashboard created while the caller's ambient workspace is "business" is not stored under "business") |
| `GET` | `/dashboards/{id}` | per access | Raw record (edit-mode source of truth) |
| `GET` | `/dashboards/{id}/render` | per access | **Core endpoint** — resolves dashboard access once, renders every block through the registry, returns `{..., cross_workspace, blocks: [{id, type, config, layout, ok, data, locked_reason}]}` |
| `PATCH` | `/dashboards/{id}` | contribute+ (edit+ for `cross_workspace`) | `{name?, icon?, cross_workspace?, blocks?}` — `blocks` is a bulk array replace; triggers a reindex for the cross-module reference lookup |
| `PUT` | `/dashboards/{id}/access` | edit | `{shared_with?, hidden_from?, contributors?}` |
| `PUT` | `/dashboards/{id}/share-underlying-data` | **owner only** (not just edit-level) | `{value: bool}` |
| `DELETE` | `/dashboards/{id}` | edit (owner/pool admin) | `409` if it's the caller's only dashboard in this workspace |
| `POST` | `/dashboards/{id}/leave` | share recipient | Remove self from a dashboard shared with you |
| `POST` | `/dashboards/shares/respond` | recipient | `{owner, dashboard_id, accept}` |
| `GET` | `/dashboards/catalog` | module users | Block-type registry metadata (label/category/`admin_only`/workspace), pre-filtered for the caller's admin status |
| `GET` | `/dashboards/references/{module}/{record_id}` | module users | "Referenced by N dashboards" — viewer-filtered so a caller never learns a dashboard exists unless they can already see it |
| `GET` | `/dashboards/members` | module users | Member display names for the share picker, mirrors `assets.py`'s `/assets/members` |
| `GET` | `/dashboards/roles` | module users | Feature-role names for the share-by-role picker |

**Block catalog** (27 types across `live_aggregate` / `record_linked` / `freeform` categories) —
Tasks/Goals (`top3_tasks`, `due_today` — both take a `sort_mode: "priority"|"date"|"alpha"` config, default `priority`, 2026-08-15; `streaks`, `goals_progress`, `single_task`), Smart Home
(`home_favourites`, personal only), Household/Team (`pool_tasks`), Calendar (`upcoming_events`,
`single_event`), Finance (`finance_activity` — asset/contact/book variants, `finance_book_report`),
Contacts (`linked_deals`, `custom_fields`, `linked_assets`), Assets (`documents`, `linked_tasks`,
`linked_contact`, `my_assets_summary`), Notes (`note_embed`), Journal (`journal_entry`), Automations
(`workflow_status`, `inbox_summary`), AI (`ai_usage_me`, `ai_usage_overview` — **admin-only**,
`recent_ai_actions`), Freeform (`text_block`, `link_button`, `heading_divider`). Every
`live_aggregate` block takes a `scope: "owner"|"viewer"` config — `"owner"` only ever resolves when
the viewer IS the owner (directly, or via the `share_underlying_data` exception's Pass 2).

**Action buttons** (2026-08-15): any block whose type declares a `recordKind` in the frontend's `blockRegistry.js` (currently Notes, Assets/Collection, Contacts, and every other list-shaped block — task/asset/contact/event/note) can carry `actions: [{id, kind: 'nav'|'status', ...}]` in its own `config`, authored via a repeater in the block-config UI. No new endpoint: `actions` rides inside the existing `config` object already returned by `GET /dashboards/{id}/render`, and a click executes through the target module's own existing endpoint directly from the frontend (`tasksApi`/`assetsApi`/`contactsApi`, the same call `status_button`/`nav_button` already make) — never a dashboard-owned write path. A new `contacts_list` block type (Contacts, `live_aggregate`) was added alongside this as the first general "list of contacts" block.

**Chrome toggles `show_card`/`show_header`** (2026-08-18): two booleans any **non-chromeless** block type's `config` can carry — same no-new-endpoint shape as `actions` above, they just ride inside the existing `config` object through the generic `PATCH /dashboards/{id}` (or the agent's `update_dashboard_block` tool). Both default to `true` when absent — `show_card` toggles the card/border background, `show_header` toggles the icon+label header when the dashboard isn't in edit mode (edit mode always shows it, regardless, since that's the only way to reach a block's ✎/✕ controls). `nav_button`/`status_button` (chromeless block types) never accept either — there's no card/header on those to toggle in the first place.

**Not yet built** (deliberately deferred, not cut from scope — see `docs/TASKS.md`): the "Referenced
by" UI hooks on non-Assets/Contacts view surfaces, Module Engagement and External Data block types, and
Spending/Completion trend blocks (need new aggregation endpoints that don't exist yet). Dashboard
Templates shipped 2026-08-09/10 (see `dashboard_templates_service.py`, `docs/MEMORY.md`) — stale here
until 2026-08-12. A Net Worth aggregation endpoint (`GET /finance/networth`) also already exists, but
has no Dashboard block wired to it yet — it currently has no frontend consumer at all (found while
fixing its currency-blending bug, 2026-08-12).

`PATCH /auth/me` also accepts `default_dashboard_id: {personal, business}` (same workspace-keyed
shape as `shortcuts`) — which dashboard opens when the Dashboard nav link is clicked.

---

## Presence

Router mounted at `/api/v1/presence`. App-wide "is this user online right now" tracking (2026-08-17),
generalized from Chat's own `POST /chat/presence` (which is conversation-scoped and unrelated to this).

### `POST /presence/ping`
Record the caller's own presence — `Layout.jsx` calls this on mount and every 30s while the tab is
visible, app-wide (not just on one page). Rate limited: 10/60s.

**Response** `{ "ok": true }`

There is deliberately **no** `GET /presence/{username}` or similar lookup endpoint — presence is only
ever meant to surface embedded in an already access-controlled read (e.g. a contact record whose
`self_of` names an online user), never queried directly for an arbitrary user.

---

## Mod Store

Router mounted at `/api/v1/mod-store` (2026-08-24). First-party module catalog + install state for
the universal module system (`module_registry.py`) — see `docs/MEMORY.md`'s 2026-08-24 entry for
the full design. Phase 1 only: the mechanism exists, but no real module has converted into
`module_packages/` yet, so every endpoint below is live but the catalog only ever lists
`coming_soon` entries for now.

### `GET /mod-store/catalog`
Admin only. Every catalog entry (`content/mod_store_catalog.json`) merged with live state:
`installed`, `uninstallable`, `version` (from the module's manifest if present), and `status`
(`coming_soon` | `available` | `error` — a module whose manifest/router failed to import shows
`error` here, not a silent gap). Rate limited: 30/60s.

### `GET /mod-store/installed`
Any logged-in user. `{ "installed": ["id", ...] }` — the marker file's contents. The frontend's own
module-loading needs this, not just admins.

### `GET /mod-store/active`
Any logged-in user. `{ "active": ["id", ...] }` — which module ids are actually registered in the
**running process** (cached on `app.state.active_module_ids` at boot), distinct from `/installed`:
between clicking Install and clicking Restart Now, `/installed` says yes but `/active` still says
no, since `register_routers()` only runs once at process start.

### `POST /mod-store/install/{module_id}`
Admin only. Validates the id against `discover_manifests()` (whitelist lookup — never used to build
a filesystem path), catalog status must be `available`, rejects if already installed. Runs the
module's `on_install()` hook if any, then flips the marker. **Does not restart anything.**
Response: `{ "ok": true, "module_id", "restart_required": true }`. Rate limited: 10/60s.

### `POST /mod-store/uninstall/{module_id}`
Admin only. 404 if not installed, 400 if the module is `uninstallable` (enforced server-side, not
just a hidden button in the UI). Flips the marker — never touches the module's Brain data or its
code on disk ("hide only, never delete"). Response shape matches install. Rate limited: 10/60s.

### `POST /mod-store/restart`
Admin only. Body: `{ "force": false }`. Restarts the app's own `logcore-app` container via the same
locked-down socket-proxy Docker mechanism `n8n_service.py`'s `restart_n8n()` already uses — this is
what actually applies an install/uninstall, never automatic. If other users currently appear online
(`presence_service.is_online()`) and `force` isn't set, returns `409` with
`{ "message", "online_users": [...] }` instead of restarting. Rate limited: 10/60s.

---

## Health

### `GET /health`
Returns `{ "status": "ok" }`. No auth required. Used by Docker healthcheck.
