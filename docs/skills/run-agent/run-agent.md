# run-agent

Send a natural language goal to the LogCore AI agent and get the result including any tool calls it made.

## Usage

```
./run.sh "goal text" [BASE_URL] [TOKEN]
```

| Argument   | Default                        | Description                              |
|------------|---------------------------------|------------------------------------------|
| goal       | required                        | Natural language instruction or question |
| BASE_URL   | `http://localhost:8000/api/v1`  | API base URL — all routes live under `/api/v1/`, see `docs/AGENTS.md`'s API Versioning section |
| TOKEN      | `$LOGCORE_TOKEN` env var        | Bearer token from `/api/v1/auth/token`   |

## Output

Prints the final answer followed by a step trace (tool calls and their outputs).

- `mode: qa` — answered directly, no tools used
- `mode: agent` — one or more tools were called

## Getting a token

The browser uses an HttpOnly cookie for auth. CLI clients use a Bearer token
obtained from the dedicated `/auth/token` endpoint:

```bash
export LOGCORE_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"..."}' | jq -r '.token')
```

## Example

```bash
./run.sh "Add a high priority task to call mom today"
./run.sh "What are my top 3 tasks?" http://myserver.local:8000/api/v1 $TOKEN
```

## Notes

- Requires `jq` and `curl`
- Each invocation mints a fresh `chat_id` (required on every `POST /chat` since 2026-08-15) via `uuidgen`, so history is not preserved between invocations (each call starts a new conversation) — this is a deliberate limitation of this quick one-shot script, not a bug
- The agent uses whatever AI provider is configured in the Admin panel
