# LogCoreOS API Reference

Base URL: `/api/v1`

All authenticated endpoints require `Authorization: Bearer <token>`.

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
  "disabled_modules": [],
  "accent_color": "#f97316",
  "dark_mode": "system",
  "background": "gradient:midnight",
  "density": "comfortable",
  "corner_style": "rounded"
}
```

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
  "corner_style": "sharp"
}
```

Valid values:
- `dark_mode`: `"system"` | `"light"` | `"dark"`
- `background`: `"none"` | `"uploaded"` | `"gradient:<id>"` where id ∈ `{none, midnight, sunset, forest, ocean, aurora, dusk}`
- `density`: `"comfortable"` | `"compact"`
- `corner_style`: `"rounded"` | `"sharp"`
- `accent_color`: any 6-digit hex like `#f97316`

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

**Response** `{ "allow_open_registration": false }`

### `PATCH /auth/admin/settings`
Update runtime admin settings.

**Body** `{ "allow_open_registration": true }`

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

**Body** `{ "email": "bob@example.com", "password": "secret", "name": "Bob", "role": "member" }`

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

---

## Chat

### `POST /chat`
Send a message to the AI with conversation history.

**Body**
```json
{
  "message": "What should I focus on today?",
  "history": [
    { "role": "user", "content": "Hi" },
    { "role": "assistant", "content": "Hello! How can I help?" }
  ]
}
```

**Response** `{ "response": "Based on your priorities..." }`

Rate limited: 20 messages per minute per IP.

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

Any authenticated member may read and create tasks. Event write operations (create/update/delete) require admin role.

### `GET /shared/tasks`
List all shared tasks. Returns all tasks regardless of due date.

### `POST /shared/tasks`
Create a shared task. `created_by` is set automatically from the auth token.

**Body** — same shape as `POST /tasks` (all optional fields apply).

### `PATCH /shared/tasks/{task_id}`
Update a shared task. Setting `status` to `done` or `skipped` records `completed_by`.

### `DELETE /shared/tasks/{task_id}`
Delete a shared task.

### `GET /shared/events`
List shared calendar events (household pool).

### `POST /shared/events`
Create a shared calendar event. Admin only. `created_by` set automatically.

### `PATCH /shared/events/{event_id}`
Update a shared event. Admin only.

### `DELETE /shared/events/{event_id}`
Delete a shared event. Admin only. Returns `204 No Content`.

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

## Health

### `GET /health`
Returns `{ "status": "ok" }`. No auth required. Used by Docker healthcheck.
