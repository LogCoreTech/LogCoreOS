# docs/skills — Dev Tools for Claude Code Sessions

These skills are for use during development sessions with Claude Code. Each has a `.md` instruction file and optional shell scripts.

| Skill | When to use |
|-------|-------------|
| `diagnose/` | Before a release or full health check — security, architecture, logic audit with severity levels |
| `run-tests/` | After any backend change, before committing — runs pytest and reports GREEN/RED |
| `run-agent/` | To send a natural-language goal to the in-app LogCore AI and see its tool trace |

## How to invoke

Tell Claude Code: "run the diagnose skill" or "run the tests". It will read the `.md` file, execute the `.sh` script, and report structured findings.

Manual:
```bash
bash docs/skills/run-tests/run.sh
bash docs/skills/diagnose/pre-check.sh
bash docs/skills/run-agent/run.sh "your goal here"
```

## Adding a new skill

1. Create `docs/skills/<skill-name>/`
2. Add `<skill-name>.md` — task definition, steps, output format
3. Add any shell scripts needed
4. Register it in this README
