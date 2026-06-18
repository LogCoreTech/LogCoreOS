# Contributing to LogCoreOS

Thank you for your interest in contributing! This document covers the basics. For a deeper understanding of the codebase, read [docs/FOR_AI.md](docs/FOR_AI.md).

---

## Getting Started

1. Fork the repo and create your branch from `master`.
2. Follow the development setup in [docs/FOR_AI.md](docs/FOR_AI.md#development-setup).
3. Run the test suite before opening a PR: `cd app/backend && pytest tests/ -v`
4. Make sure `npm run build` passes in `app/frontend/`.

## Branching

- `master` is the stable branch. PRs merge here.
- Name branches descriptively: `feature/export-brain`, `fix/leap-year-bug`, `docs/api-reference`.

## Code Style

**Backend (Python)**
- Follow PEP 8. No line longer than 100 chars.
- Type annotations on all public functions.
- No bare `except:` — catch specific exceptions.
- All file writes go through `write_json()` / `write_markdown()` — never `open(..., 'w')` directly.

**Frontend (JavaScript/React)**
- Functional components with hooks only.
- All API calls through `lib/api.js` — no raw `fetch()` in components.
- Tailwind utility classes only. No inline `style={}` unless strictly necessary.
- No `console.log` in committed code.

## Commit Messages

Use the imperative mood, present tense:
- `Fix leap year bug in recurring task scheduler`
- `Add promote-to-admin endpoint`
- `Update API base URL to /api/v1`

## Pull Requests

- One logical change per PR.
- Fill out the PR template — the test plan matters.
- PRs that touch auth, file writes, or path construction require extra attention to security.

## Reporting Issues

Use the GitHub Issue templates:
- **Bug Report** — for something broken
- **Feature Request** — for new functionality

## Security Vulnerabilities

Do **not** open a public issue for security vulnerabilities. Email the maintainers directly or use GitHub's private vulnerability reporting.

## License

By contributing, you agree that your contributions will be licensed under the same license as this project.
