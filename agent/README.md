# LogCoreOS Agent Layer

This directory defines the skills available to any AI agent working on LogCoreOS. Skills are tool-agnostic — any agent (Claude, GPT, local model, custom) can read and execute them.

Read `docs/FOR_AI.md` before using any skill. It is the authoritative guide covering architecture, conventions, and safety rules.

---

## Skills

Each skill lives in its own folder containing the instruction file and all scripts it needs to run.

```
agent/skills/
├── run-tests/
│   ├── run-tests.md    — instructions: what to run, how to interpret output, how to report
│   └── run.sh          — executes pytest and prints a structured GREEN / RED report
│
└── diagnose/
    ├── diagnose.md     — instructions: full security / architecture / strategy / logic audit
    └── pre-check.sh    — automated script: runs the checkable assertions before the AI audit
```

| Skill | When to use |
|-------|-------------|
| `run-tests` | After any code change, before committing, to verify nothing broke |
| `diagnose` | After a batch of changes, before a release, or for a full health check |

---

## How to use a skill

1. Read the skill's `.md` file — it defines the full task
2. Run any `.sh` scripts first (they handle the automatable checks)
3. Pass the script output + the `.md` instructions to your agent
4. The agent applies the output format defined in the `.md` and reports findings

---

## Adding a new skill

1. Create `agent/skills/<skill-name>/`
2. Add `<skill-name>.md` — task definition, steps, output format
3. Add any shell scripts the skill needs alongside it
4. Register it in this README
