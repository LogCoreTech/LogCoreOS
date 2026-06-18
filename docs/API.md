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
  "token": "<jwt>",
  "name": "Alice",
  "role": "member",
  "disabled_modules": [],
  "timezone": "UTC"
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
  "disabled_modules": []
}
```

### `PATCH /auth/me`
Update own profile (timezone).

**Body** `{ "timezone": "America/New_York" }`

**Response** `{ "ok": true, "timezone": "America/New_York" }`

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

## Health

### `GET /health`
Returns `{ "status": "ok" }`. No auth required.
