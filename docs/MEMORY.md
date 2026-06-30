# MEMORY.md — LogCoreOS Long-Term Memory

Stable knowledge about this project: design decisions, security rules, and lessons learned. Update this file when a decision is made that should survive session restarts.

---

## What LogCoreOS Is

LogCoreOS is a self-hosted, open-source, AI-native life operating system. It gives individuals and families a private Brain (Markdown + JSON files) that an AI layer can read and act on.

**Two products:**
- **LogCore Brain** (`brain/`) — Free and open source. Markdown + JSON files. Works with any AI.
- **LogCore App** (`app/`) — FastAPI backend + React frontend, installable as a PWA.

**End goal:** A working, deployed, self-hosted platform where users control all their data, no cloud required.

---

## Core Design Decisions

**Brain = filesystem, no database**
User data lives in `brain/USERS/{name}/` as Markdown and JSON files. No SQL, no ORM.
**Why:** Human-readable, AI-friendly, vendor-agnostic, fully portable. User can take the Brain folder anywhere and any AI can read it.
**How to apply:** Never propose storing user data in a database. If a new feature needs persistence, add a JSON file under the appropriate Brain path.

**Atomic writes always**
All Brain file writes use `write_json()` and `write_markdown()` from `services/file_service.py`. These use `tempfile.mkstemp` + `os.replace()` for POSIX atomic writes.
**Why:** Prevents partial writes from crashing the app or corrupting data.
**How to apply:** Never use `open(..., 'w')` directly for Brain files. Always use the file_service helpers.

**JWT JTI revocation**
Tokens carry a unique `jti` field. Logout revokes the JTI in memory (`_revoked_jtis`) and persists to `auth.json`. On startup, `_bootstrap_revoked_jtis()` reloads the blacklist from disk.
**Why:** Stateless JWTs can't be invalidated without a revocation mechanism. JTI blacklist gives us true logout.
**How to apply:** Never skip JTI checks. If modifying auth, ensure the JTI is checked in `get_current_user()`.

**Module system: frontend + backend must stay in sync**
`ALL_MODULES` in `app/frontend/src/lib/constants.js` defines the module registry. Each module `id` must exactly match the string used in `require_module(module_id)` on the backend. Modules with `nav: false` and no `to` field appear in the Admin → RolesCard for toggling but are hidden from the sidebar and mobile drawer — used for sub-features that gate content within a page rather than a full page route.
**Why:** Mismatch causes silent access failures or broken feature gating. `nav: false` modules must still be in `ALL_MODULE_IDS` in `features_service.py`.
**How to apply:** When adding a module, update both `constants.js` AND the backend router's `require_module()` call. Current IDs: `dashboard`, `tasks`, `calendar`, `household`, `notes`, `journal`, `chat`, `automations`, `automations_business`, `home`, `team`.

**Dynamic CORS reads hosting.json at request time**
`DynamicCORSMiddleware` in `main.py` reads `brain/hosting.json` at each request, not at startup.
**Why:** Allows the Admin → Hosting panel to take effect immediately without a container restart.
**How to apply:** Never cache the CORS origin in memory. Read `hosting_service.effective_domain_url()` per request.

**Runtime hosting config always wins over env vars**
`cookie_secure` and `trust_proxy_headers` can be set in `docker/.env` (defaults) but are overridden at runtime by `brain/hosting.json`. Always use `hosting_service.effective_cookie_secure()` and `effective_trust_proxy_headers()` — never read `settings.*` directly in request-serving code.

**Feature roles are separate from auth roles**
Auth roles (`admin`, `member`, `guest`) control who can access admin endpoints. Feature roles (custom, e.g. `cleaner`) control which app modules are visible. They are stored and managed independently. `guest` is the default feature role for new users (security default). `member` is the internal fallback when a feature role goes missing.

---

## Security Rules

1. **Never trust user input as file paths.** Always resolve through `user_path()` from `file_service.py`.
2. **Brain file content injected into AI prompts must be wrapped in `<brain_data>` XML tags** to prevent prompt injection. See `routers/chat.py:_safe()`.
3. **`trust_proxy_headers`** defaults to `False`. Only enable when there is a trusted reverse proxy in front of the app.
4. **`SECRET_KEY`** must be changed from the default before any network exposure. `launch.sh` generates one automatically.
5. **Passwords** are bcrypt-hashed. Never store or log plaintext passwords.
6. **`brain/_system/auth.json` and `docker/.env` must never be committed.** Both are in `.gitignore`.
7. **`cookie_secure`** should be `true` in any HTTPS deployment. The Admin → Hosting panel sets this at runtime.
8. **Self-hosters must never see the Infisical card** in Admin unless a token was configured at deploy time. Env var tokens cannot be cleared via UI — only file-sourced tokens can be cleared.
9. **Rate limits are enforced on all endpoints.** Login: 5/5 min; register: 3/hour; general reads: 30/min; writes: 10/min; admin ops: 20/min. Always apply `rate_limit(count, window_secs)` to new endpoints.
10. **Security headers are added by `SecurityHeadersMiddleware`** in `main.py`: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Cache-Control: no-store` on all `/api/*` responses.

---

## Environment Variables (config.py)

All env vars are defined in `app/backend/config.py` via Pydantic Settings and read from `docker/.env`.

| Variable | Default | Purpose |
|---|---|---|
| `BRAIN_PATH` | `/data/brain` | Volume mount path for Brain files |
| `SECRET_KEY` | `change-me-in-production` | JWT signing key — **must be changed** |
| `AI_PROVIDER` | `anthropic` | `anthropic` or `openai` (OpenAI-compatible) |
| `ANTHROPIC_API_KEY` | `""` | Set via env or Admin UI (stored in `brain/ai_settings.json`) |
| `AI_MODEL` | `claude-sonnet-4-6` | Model identifier |
| `AI_API_KEY` | `""` | For non-Anthropic providers |
| `AI_BASE_URL` | `""` | Custom endpoint; empty = provider default |
| `TAVILY_API_KEY` | `""` | Web search in chat research mode |
| `NTFY_URL` | `http://ntfy:80` | Internal ntfy notification endpoint |
| `COOKIE_SECURE` | `True` | Set `False` for local HTTP dev |
| `ALLOWED_ORIGINS` | `*` | Comma-separated allowed CORS origins |
| `SCHEDULER_TIMEZONE` | `America/Chicago` | IANA timezone for all scheduler jobs |
| `MORNING_DIGEST_HOUR` | `6` | Hour (0–23) for daily digest job |
| `OVERDUE_CHECK_HOUR` | `19` | Hour (0–23) for overdue + weekly + goal drift jobs |
| `ALLOW_OPEN_REGISTRATION` | `False` | `True` = open signup (dev/demo only) |
| `TRUST_PROXY_HEADERS` | `False` | `True` when behind nginx/Caddy |

---

## Known Gotchas

**Docker volume path for frontend dist:**
The backend resolves the frontend dist as `Path(__file__).parent.parent / "frontend" / "dist"`. Since `main.py` is at `/app/main.py` inside the container, `parent.parent` is `/`. The volume mount in `docker-compose.yml` must be:
```yaml
- ../app/frontend/dist:/frontend/dist   # correct
# NOT: ../app/frontend/dist:/app/frontend/dist  (breaks static file serving)
```

**Health check URL:**
The correct health check path is `/api/v1/health`. The old path `/api/health` does not exist.

**Docker socket permissions:**
The app user must be in the `docker` group. After `sudo usermod -aG docker <username>`, the user must log out and back in (or `newgrp docker`). In the current dev environment, use `echo "12345" | sudo -S docker <cmd>` if the group isn't active.

**nvm and Node.js:**
nvm is a version manager — installing nvm does not install Node.js. Run `nvm install <version>` separately. Node.js is loaded via `.bashrc`; open a new terminal or source `.bashrc` before running `launch.sh`.

**Runtime hosting config vs env vars:**
`cookie_secure` and `trust_proxy_headers` can be in `docker/.env` (defaults) OR overridden at runtime by `brain/hosting.json`. The runtime value always wins. Never read `settings.*` directly in request-serving code.

**Backend code changes require Docker image rebuild:**
Python code is baked into the Docker image at build time. Any change to `app/backend/` requires:
```bash
bash launch.sh --skip-build   # rebuilds image only, skips npm
```
Running without `--reload` will not pick up file changes.

**Mobile viewport height — use `100dvh` not `100vh`:**
`100vh` on mobile includes browser chrome that appears/disappears while scrolling, making fixed elements overlap. Always use `h-[100dvh]` on the root container, not `h-screen` / `h-[100vh]`.

**Flex scroll containment — always add `min-h-0` to scrollable flex children:**
Without `min-h-0`, the browser defaults `min-height: auto`, letting the child grow to full content size and overflow its parent instead of scrolling. Required on the messages list in `Chat.jsx` and any other scrollable flex child. Never remove it.

**PWA standalone mode — `Cache-Control: no-cache` on `index.html`, NOT `no-store`:**
`no-store` prevents the browser from storing `index.html` at all, breaking iOS's ability to detect the page was saved to the home screen. The SPA catch-all in `main.py` must send `Cache-Control: no-cache`.

**httpOnly cookie timing on mobile login:**
After `POST /auth/login`, there is a timing gap before the cookie is available for subsequent requests on mobile. Never fire parallel requests immediately after login. Use the login response directly (it returns the same user object as `/me`) and then make follow-up calls sequentially.

**Docker tunnel container conflict:**
If a container named `logcore-tunnel` is orphaned (from a crashed session), `launch.sh` will fail with a "container name already in use" conflict. Fix: `echo "12345" | sudo -S docker rm -f logcore-tunnel` then relaunch.

---

## Key Decisions Log

- **2026-06-25** — Feature Flags + RBAC system added. `guest` is the security default for new users; `member` is the internal fallback when a feature role goes missing. Both are protected built-in roles.
- **2026-06-25** — Shared React state lifted to `Admin` component so `UsersCard` and `RolesCard` see the same roles list in real time without separate fetches.
- **2026-06-25** — Auth role and feature role are kept fully separate systems. Auth role controls endpoint access; feature role controls module visibility.
- **2026-06-29** — Automations module added. n8n is bundled as `logcore-n8n` Docker service. Personal workflows stored in `brain/USERS/{name}/Automations/workflows.json`; business workflows in `brain/_system/automations_index.json`. Business workflow JSON files are NOT committed to the repo — admins import them via the Admin UI on managed servers. This keeps self-hosters from receiving business content automatically (the trade-off of open-source).
- **2026-06-29** — Infisical secrets are written to `docker/n8n.env` at startup (when Infisical is configured) so n8n workflows can reference them as `{{ $env.VAR_NAME }}`. Admin → n8n card can trigger a re-sync and restart.
- **2026-06-29** — Setup wizard `show_profile_type` is now gated on `features.json` existence (first-user only). Subsequent users skip the Personal/Business question — their choice would be a no-op since `init_features()` is idempotent.
- **2026-06-29** — `automations` and `automations_business` are two separate module IDs. `automations` gates the page + Personal tab; `automations_business` gates only the Business tab within the page. Default: personal members get `automations` on, `automations_business` off; business members get both on. This allows granular per-user tab control without a second nav entry.
- **2026-06-29** — Home Assistant integration added as `home` module. Config stored in `brain/_system/ha_config.json` (url + token). Service: `ha_service.py`. Router: `routers/home.py`. Frontend: `pages/Home.jsx` (domain tabs, entity tiles, scenes, automations). Dashboard widget shows pinned favourite entities with quick toggle. 4 AI tools added to agent_service.py (`get_home_state`, `control_home_device`, `activate_scene`, `trigger_home_automation`); only injected into tool list when HA is configured. User favourites stored per-user at `brain/USERS/{name}/Home/favourites.json`.
- **2026-06-29** — Business workflow auto-sync via stub files. Stub files (`*.stub.json`) committed to `app/backend/automations_stubs/` contain only name + key + tags — no workflow logic. On startup (90 s delay for n8n to boot) and every 6 hours, the app fetches actual workflow JSONs from `WORKFLOWS_BASE_URL/{key}.json` using `WORKFLOWS_TOKEN` (both from Infisical), reconciles against n8n (create new / update changed via content hash / delete removed stubs). Recommended source: private GitHub repo + fine-grained PAT (`Contents: Read-only`). Self-hosted instances without those Infisical secrets skip silently. Admin can force an immediate sync via the "Sync Workflows Now" button in Admin → n8n card or `POST /api/v1/automations/n8n/sync-workflows`.
