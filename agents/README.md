# LogCoreOS Agent Layer

This directory defines the skills and context available to any AI agent working on LogCoreOS.

## Skills

Skills are self-contained task definitions in `agents/skills/`. Each file describes what to do, how to do it, and how to report results. They are tool-agnostic — any agent (Claude, GPT, local model) can read and execute them.

| Skill | File | When to use |
|-------|------|-------------|
| `run-tests` | `skills/run-tests.md` | After code changes, before committing, to verify nothing is broken |
| `diagnose` | `skills/diagnose.md` | After a batch of changes, before a release, for a full health check |

## How to use skills

An agent should:

1. Read the skill file to understand the task
2. Execute any commands listed
3. Apply the output format described in the skill
4. Cross-reference findings against `docs/FOR_AI.md` (the project's principles)

## Project context

The authoritative guide for any agent working on this codebase is `docs/FOR_AI.md`. It covers architecture, conventions, safety rules, and how to run the project. Read it before executing any skill.
