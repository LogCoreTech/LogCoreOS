# run-agent

Send a natural language goal to the LogCore AI agent and get the result including any tool calls it made.

## Usage

```
./run.sh "goal text" [BASE_URL] [TOKEN]
```

| Argument   | Default                    | Description                              |
|------------|----------------------------|------------------------------------------|
| goal       | required                   | Natural language instruction or question |
| BASE_URL   | `http://localhost:8000/api` | API base URL                             |
| TOKEN      | `$LOGCORE_TOKEN` env var   | Bearer token from `/api/auth/login`      |

## Output

Prints the final answer followed by a step trace (tool calls and their outputs).

- `mode: qa` — answered directly, no tools used
- `mode: agent` — one or more tools were called

## Example

```bash
./run.sh "Add a high priority task to call mom today"
./run.sh "What are my top 3 tasks?" http://myserver.local:8000/api $TOKEN
```

## Notes

- Requires `jq` and `curl`
- History is not preserved between invocations (each call starts fresh)
- The agent uses whatever AI provider is configured in the Admin panel
