# Releasing LogCoreOS

Steps to cut a release. Work is spread across parallel sessions, so no single session "owns" this — whoever cuts the release runs the whole checklist, don't assume an earlier step was already done.

1. **Confirm `[Unreleased]` in `CHANGELOG.md` is actually ready to ship** — nothing half-finished sitting under it.
2. **Bump the version** in two places: `VERSION` (repo root) and `app/frontend/package.json`'s `"version"` field. Leave `app/frontend/package-lock.json`'s own version stamp untouched — it self-corrects on the next `npm install` and has never been part of this checklist.
3. **Stamp `CHANGELOG.md`**: insert `## [X.Y.Z] — YYYY-MM-DD` directly under `## [Unreleased]`, leaving a fresh empty `[Unreleased]` section above it. Everything that was sitting under `[Unreleased]` now reads as shipped under the new version heading.
4. **Add a `whats_new` entry to `app/backend/content/help.json`** (top of the `whats_new` array — newest first) — `version`, `date`, and a `highlights` array of plain-language, benefit-first bullets condensed from the CHANGELOG (roughly 5-10 depending on how much shipped; see past entries for tone — concrete and specific, not marketing copy). This one entry powers three user-facing surfaces at once: the Help page's What's New section, the one-time broadcast notification to every user's inbox (`announce_if_updated()` at boot), and the dismissible banner. **Skipping it means the release ships silently** — this was missed once already (0.4.0, 2026-07-19) and is the easiest step to forget since it lives in a backend content file, not an obviously release-related one.
5. **If a new module shipped this release, add its own `help_section`** in `help.json`'s `sections` array too — separate from the `whats_new` step, this is the module's persistent Help-page content (see `docs/MODULE_AUTHORING.md`).
6. **Commit** as `chore(release): bump version to X.Y.Z`, with a body summarizing what's being stamped (see `git log` for past examples — e.g. the 0.7.1 and 0.8.0 bump commits).
7. **Do NOT create the git tag.** The owner tags releases themselves — never run `git tag` for a version tag on their behalf, even if asked to "follow the checklist," unless they explicitly ask for the tag itself in that request.
8. **Generate a GitHub release title and body for the owner to copy** when creating the release on GitHub:
   - **Title**: `vX.Y.Z — <short thematic subtitle>` (e.g. `v0.8.0 — Security Hardening, Trash & Bulk Actions, AI Settings Overhaul`) — a few words capturing the release's biggest themes, not every bullet.
   - **Body**: a Markdown-formatted version of the new CHANGELOG section (`### Added`/`### Fixed`/`### Removed`/`### Security`, whichever are non-empty), reproduced close to verbatim — this is for GitHub's own release-page audience (more technical/complete than the in-app `whats_new` highlights, which are the user-facing condensed version of the same release).
   - Present this directly in the conversation for the owner to copy — don't create the GitHub release yourself (that's a `gh release create` action against the real public repo, outside what this checklist covers and not something to do without being asked).
9. **Don't push** the commit unless explicitly asked — commits are session-scoped (see memory: commits-are-session-scoped).

## Reference: past release commits

`git log --oneline --all -- VERSION` finds every past version bump. `git show <sha> -- CHANGELOG.md VERSION app/frontend/package.json app/backend/content/help.json` shows exactly what one bump touched — useful as a concrete template when in doubt about format.
