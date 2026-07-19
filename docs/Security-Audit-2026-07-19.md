# LogCoreOS — Security Audit

**Date:** 2026-07-19
**Scope:** Full-depth audit — application code (auth, authorization, path safety, injection, secrets handling) **and** infrastructure/dependency/supply-chain layer (Docker Compose, scripts, third-party images, dependency CVEs, security headers).
**Method:** Ran the project's own `docs/skills/diagnose/pre-check.sh`, then a manual sweep against the `diagnose.md` security rubric plus an infra/dependency review. Every finding below cites a file:line that was read directly. Candidate findings were cross-checked against the intentional-design exclusion lists in `docs/skills/diagnose/diagnose.md`, `docs/MEMORY.md`, and `SECURITY.md`.
**Deliverable:** Report only — no code or configuration was changed.

---

## Diagnostic Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 5 |
| MEDIUM   | 6 |
| LOW      | 3 |

> **Update — data-theft / cross-tenant threat pass (added after initial report).** A follow-up pass focused specifically on a *malicious authenticated user (or hostile self-registrant) trying to steal another user's data* — the most important threat for an app that holds people's whole lives. Result: the core cross-tenant isolation is **well-built and was verified sound** (see "Cross-Tenant Data-Theft Threat Model" under Verified Sound). One new HIGH finding surfaced — a bulk asset-export endpoint reachable with the shared automation token (A2 below).

**Overall verdict: NEEDS ATTENTION.**

The **application code is genuinely strong** — the core auth/authorization/path-traversal/injection defenses are well built and were verified sound (see "Verified Sound" at the end). Every material risk is concentrated in the **deployment/infrastructure layer** (the bundled Docker stack, secret handling, and installer defaults) plus **one application finding** (an unthrottled login endpoint) and **stale dependencies**. Nothing here indicates a currently-exploited hole; these are hardening gaps that matter most the moment an instance is exposed to the public internet.

---

## Section A — Application-Level Security

### [HIGH] [rate-limiting] app/backend/routers/auth.py:280
**Issue:** `POST /auth/token` (CLI/programmatic Bearer-token login) calls `auth_service.authenticate(email, password)` with **no rate-limit dependency**. Its sibling `POST /auth/login` (auth.py:244) is throttled at `_login_limit` = 5 attempts / 5 min. Because both endpoints perform the identical credential check, an attacker can brute-force passwords through `/auth/token` at unlimited speed, completely bypassing the login throttle.
**Fix:** Add `_rl: None = Depends(_login_limit)` to `get_token()` exactly as `/login` has it. Consider sharing one rate-limit bucket keyed on email so the two endpoints can't be used to double the allowance.

### [HIGH] [data-exfiltration / broken-object-authorization] app/backend/routers/assets.py:337-349 (+ _automation_store, assets.py:315-321)
**Issue:** `GET /automation/assets?user=<name>&workspace=<ws>` returns `assets_service.list_assets(store, store_ws)` — a **full dump of the named user's entire assets store** — gated only by the shared instance-wide automation token. `_automation_store()` accepts **any real user's name** (it only checks the user exists), so a single valid token reads *every* user's assets: subdivisions, parcels, vehicles, equipment, linked contact IDs, comments, and template field values. This directly contradicts the app's own stated posture: the Contacts automation API was *deliberately* built as write-only with only a single-contact dedup lookup and no list/export — its docstring says "a leaked token cannot dump the contact base" (contacts.py:874-875). Assets has exactly the bulk-export endpoint that Contacts refuses to have. The automation token is one static secret shared across the whole instance, stored in `brain/_system/automations_config.json` and provisioned to the n8n container — and the infra findings in Section B (n8n exposed on `:5678` with default keys, Infisical secrets fanned out into `docker/n8n.env`, unencrypted `brain/` backups) give it several realistic leak paths. Once the token leaks, this endpoint is a turnkey "download every user's assets" tool. (Rated HIGH rather than CRITICAL only because it requires the token, which is admin-only to retrieve, timing-safe compared, and rotatable.)
**Fix:** Bring Assets in line with Contacts — remove the arbitrary-`user` list endpoint, or restrict `_automation_store()` to the pool pseudo-users (`_team`/`_household`) only for read operations, or replace the bulk list with a narrow dedup/lookup-by-external-id call. If a per-user automation read is genuinely required, scope the token per-user instead of one instance-wide master token.

### [MEDIUM] [transport-security] app/backend/main.py (SecurityHeadersMiddleware)
**Issue:** `SecurityHeadersMiddleware` sets `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, and `Cache-Control: no-store` on `/api/*`, but sets **no `Content-Security-Policy`, no `Strict-Transport-Security` (HSTS), and no `Permissions-Policy`.** The SPA loads Google Fonts from external origins with no CSP, so any future XSS in the React app has zero CSP containment, and with no HSTS a downgrade/plain-HTTP session (the installer default — see A/MEDIUM cookie note) is never force-upgraded.
**Fix:** Add a `Content-Security-Policy` (at minimum `default-src 'self'`, `script-src 'self'`, `connect-src 'self'`, plus the two Google Fonts hosts), and add `Strict-Transport-Security: max-age=31536000; includeSubDomains` on responses when the request is HTTPS / a domain is configured in `hosting.json`.

### [MEDIUM] [cors / insecure-default] app/backend/main.py (DynamicCORSMiddleware) + config.py:43
**Issue:** When `ALLOWED_ORIGINS` is unset it defaults to `"*"`, and `DynamicCORSMiddleware` then reflects **any** request `Origin` while also emitting `Access-Control-Allow-Credentials: true` — the classic reflected-origin-with-credentials pattern. This is a *documented* LAN-friendly default (MEMORY.md Security Rule; `main.py` logs a startup warning), and the middleware correctly switches to a single exact-match origin once an admin sets a domain in Admin → Hosting. It is flagged here (not suppressed) because a fresh install exposed to the internet **before** that hardening step is cross-origin-credential-readable by any site.
**Fix:** Treat this as "known tradeoff, startup-warned." To close it fully, have `main._startup_checks()` refuse to start (or refuse to serve non-localhost) when `ALLOWED_ORIGINS="*"` *and* a non-loopback bind is detected, rather than only logging a warning.

### [MEDIUM] [fail-open startup] app/backend/main.py (_startup_checks)
**Issue:** `_startup_checks()` logs a warning for `ALLOWED_ORIGINS=*`, a warning for `COOKIE_SECURE=false`, and a `logger.critical` banner when `SECRET_KEY` is still the `"change-me-in-production"` placeholder (config.py:9) — but **none of these block startup**. A production deploy that never hardened its `.env` runs fully, silently, with a known-default signing key (forgeable JWTs for any user, including admin).
**Fix:** Hard-fail (`sys.exit(1)`) on the default `SECRET_KEY` when the app is not bound to loopback / not in an explicit dev mode. Keep the CORS/cookie items as warnings or gate them behind the same non-loopback check.

---

## Section B — Infrastructure / Dependency / Supply-Chain Security

### [CRITICAL] [container-escape] docker/docker-compose.yml:12
**Issue:** The host Docker socket is bind-mounted into the internet-facing `app` container (`/var/run/docker.sock:/var/run/docker.sock:ro`, with `group_add` for the docker GID). The `:ro` flag only makes the *mount* read-only — it does **not** restrict the Docker Engine API. The backend already uses the Docker SDK (`n8n_service.py`, and `routers/auth.py` for the tunnel container), so any RCE in the FastAPI process — the single most attacker-exposed component in the stack — can create a privileged container that bind-mounts host `/`, i.e. **app compromise ≈ full host root.** This is a deliberate design choice (the app manages the n8n/cloudflared lifecycle), but it is the highest-impact risk in the deployment.
**Fix:** Do not give the web app direct socket access. Put container-lifecycle operations behind a minimal privileged sidecar/broker with a tiny fixed command surface (start/stop/restart named containers only), or a socket-proxy (e.g. tecnativa/docker-socket-proxy) restricted to the specific container + endpoints needed. At minimum add `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, and a read-only rootfs to the `app` service to raise the bar on the initial RCE.

### [HIGH] [secret-exposure] app/backend/services/infisical_loader.py:~130 → services/n8n_service.py:274-281
**Issue:** After Infisical fetches secrets, `load_infisical_secrets()` calls `n8n_service.write_n8n_env(secrets)`, and `write_n8n_env()` writes **every** fetched key/value pair — not just n8n-scoped ones — as plaintext `KEY=VALUE` lines into `docker/n8n.env` (verified: `lines = [f"{k}={v}" for k, v in secrets.items()]`). That file is loaded into the n8n container via `env_file:`, so any secret in the vault (e.g. `SECRET_KEY`, `ANTHROPIC_API_KEY`, `WORKFLOWS_TOKEN`) becomes readable by every n8n workflow and n8n admin user, and persists unencrypted on the host. Separately, `load_infisical_secrets()` injects all fetched keys straight into `os.environ` with no allow-list, so an Infisical secret named e.g. `TRUST_PROXY_HEADERS` would silently override deployment config.
**Fix:** Pass `write_n8n_env()` an explicit allow-list of n8n-relevant keys only. Apply the same allow-list (or a `N8N_`/known-key prefix filter) before injecting Infisical values into `os.environ`.

### [HIGH] [weak-default-credentials] docker/docker-compose.yml:~66-77
**Issue:** The bundled n8n service ships `N8N_API_ENABLED: "true"`, `N8N_BASIC_AUTH_ACTIVE: "false"`, `N8N_API_KEY: ${N8N_API_KEY:-logcore-n8n-key}`, and `N8N_ENCRYPTION_KEY: ${N8N_ENCRYPTION_KEY:-change-me-n8n}`, with port `5678` published to `0.0.0.0`. An operator who never overrides these in `docker/.env` runs an internet-reachable n8n with a well-known API key and a well-known credential-encryption key — full workflow read/write and decryption of any stored n8n credentials, entirely bypassing the app's own auth.
**Fix:** Remove the insecure compose defaults so the stack refuses to start n8n without operator-set keys (or have `launch.sh` generate strong random values into `.env`, as it already does for `SECRET_KEY`). Bind n8n/ntfy ports to `127.0.0.1:` rather than `0.0.0.0` since they're reached internally or via the tunnel.

### [HIGH] [outdated-dependency] app/backend/requirements.txt:3,6
**Issue:** `python-jose==3.3.0` predates 3.4.0, which fixed an algorithm-confusion advisory (GHSA-6c5p-j8vq-pqhj) and a JWE decompression-bomb DoS (GHSA-cjwg-qfpm-7377). Impact is *reduced* here because `decode_token()` pins `algorithms=[settings.algorithm]` and independently rejects a mismatched unverified-header `alg` before decoding (verified sound in auth_service.py:239-250) — but the vulnerable library is still present. `python-multipart==0.0.9` predates 0.0.18, which fixed a Content-Type/boundary-parsing ReDoS (GHSA-59g5-xgcq-4qw3) reachable on any multipart form/file upload.
**Fix:** Bump `python-jose>=3.4.0` and `python-multipart>=0.0.18`; re-run the test suite. These are low-risk version bumps.

### [MEDIUM] [supply-chain] docker/docker-compose.yml (image tags)
**Issue:** `cloudflare/cloudflared:latest`, `binwiederhier/ntfy` (implicit `:latest`), and `docker.n8n.io/n8nio/n8n:latest` are all unpinned. Every `docker compose up --build` / `update.sh` run can silently pull a different, unaudited upstream image — no reproducibility and no rollback point for a bad/backdoored upstream tag.
**Fix:** Pin each third-party image to a specific version (ideally a digest, `image@sha256:...`) and bump deliberately.

### [MEDIUM] [dependency-pinning] app/backend/requirements.txt:10,11,15
**Issue:** `anthropic>=0.50.0`, `openai>=1.0.0`, and `docker>=7.0.0` are pinned with a lower bound only — no upper bound — so a fresh install can pull a future major release with breaking or vulnerable changes. Not reproducible.
**Fix:** Add upper bounds (e.g. `anthropic>=0.50.0,<1.0.0`) or pin exact versions like the rest of the file.

### [MEDIUM] [secrets-at-rest] docker/backup.sh
**Issue:** `backup.sh` archives the entire `brain/` directory into `backups/*.tar.gz` with no encryption. Those tarballs contain `brain/_system/auth.json` (bcrypt password hashes), `Finance/simplefin.json` (read-only bank-data access URLs), and any Infisical/VAPID key material. The suggested cron line copies this sensitive material around in cleartext-adjacent form.
**Fix:** Encrypt the archive (e.g. `age`/`gpg` to an operator key), or at minimum document that backup tarballs are secret-grade and must be stored encrypted with restrictive permissions.

### [MEDIUM] [insecure-installer-default] launch.sh (generate_env)
**Issue:** `generate_env()` writes `ALLOWED_ORIGINS=*` and `COOKIE_SECURE=false` into every freshly generated `docker/.env`. Combined with Section A's CORS and startup-check findings, a first-time install is insecure-by-default until the admin manually visits Admin → Hosting. (It does correctly auto-generate a strong random `SECRET_KEY` here — good.)
**Fix:** Default `COOKIE_SECURE=true` and leave `ALLOWED_ORIGINS` empty (deny cross-origin) unless the operator opts into LAN mode explicitly; surface a one-line "LAN dev mode vs. exposed mode" prompt in the installer.

### [LOW] [supply-chain] launch.sh:~170,185,189
**Issue:** `install_deps()` uses `curl -fsSL https://get.docker.com | sudo sh` and the equivalent NodeSource `curl ... | sudo -E bash -`. Standard vendor bootstrap pattern, only runs on explicit `--install-deps`, and TLS is not disabled — but it's trust-on-first-use with no checksum/signature verification of the fetched script.
**Fix:** Document the pattern, or fetch → checksum-verify → execute for the pinned installer scripts.

### [LOW] [supply-chain] update.sh (do_update)
**Issue:** The auto-update path runs `git pull origin master` and immediately rebuilds/restarts (with a git-reset rollback on health-check failure). It trusts `origin` unconditionally — no GPG-signed-tag or commit-signature verification before deploying pulled code. A compromised upstream or a MITM on the git transport (mitigated by HTTPS, but not defense-in-depth) would auto-deploy. The per-minute update-check crontab (`launch.sh install_update_cron`) keeps this path always-on.
**Fix:** Verify a signed tag/commit before building, and/or require an explicit admin confirmation (the `pending_update` flag already provides a human gate — lean on it rather than fully automatic pulls).

### [LOW] [dev-tooling-staleness] app/frontend/package.json:28,21
**Issue:** `vite ^5.3.1` (5.x had dev-server path-traversal advisories fixed in later 5.4.x; current major is 6/7) and `eslint ^8.57.0` (EOL; v9 is current). Both are dev-only, so runtime exposure is minimal (the Vite dev server only matters if bound beyond localhost), but they're stale for supply-chain hygiene.
**Fix:** Upgrade on the next maintenance pass; low urgency.

---

## Verified Sound (checked, not flagged)

### Cross-Tenant Data-Theft Threat Model (verified)

Threat: an authenticated user (or a hostile self-registrant) trying to read another user's Brain — tasks, finance, contacts/PII, notes, journal, assets. This was traced directly in code and holds up:

- **No IDOR on any data module.** Finance (`finance_service.find_book`:432), Assets (`assets_service.find_asset`:1303), Contacts (`contacts_service.find_contact`:339), and Notes (`notes_service.find_note_store`:368) all use the identical confined-lookup pattern: a supplied resource ID is only ever looked up within `stores = [viewer, workspace_pool] + sharers_for(viewer)`, and access is re-resolved per record via the module's access gate. Passing a stranger's `book_id` / `asset_id` / `contact_id` / note path resolves to nothing — there is no "scan all users for this ID" path anywhere.
- **The share index can't be poisoned.** `sharers_for(...)` (finance/assets/contacts index) is a derived cache of "who has shared *with* this viewer." Only a resource's owner can write share entries, so an attacker cannot insert themselves as a recipient of a victim's data to make the victim appear in their `sharers_for` set.
- **Access gates enforce the specificity ladder in code, not just docs.** `_resolve_book_access` (finance_service.py:278), `_resolve_grant`/`_share_access` (assets_service.py:570), and `resolve_access` (contacts_service.py:258) all implement the by-name-overrides-group / hidden_from-beats-shares / admin-vs-pool_edit ladders that MEMORY.md records as previously-buggy — re-verified consistent here.
- **The AI agent cannot be steered cross-tenant.** `_execute_tool` (agent_service.py:1262) binds every store operation to `user["name"]` (the authenticated caller); the model's tool `inputs` supply only data and IDs, never the store owner. `list_brain_files`/`read_brain_file` use `ws_path(user["name"], ...)`. A prompt-injection payload in shared/Brain content cannot make the agent read another user's store.
- **Export is self-scoped.** `GET /api/v1/user/export` (export.py:19) zips `user_path(current_user["name"])` only — no user parameter — and is rate-limited 2/hour. Contacts CSV export (`contacts.py:253`) returns only `list_visible_contacts(...)` for the caller.
- **User-listing endpoints strip secrets** (auth_service.py:194-198, routers/auth.py:477-482) — password hashes never leave the server.

The **one** hole in this threat model is finding **A2** above: the Assets automation list endpoint, which is a bulk cross-user read — but reachable only with the shared automation token, not via a normal user session.

### Other defenses reviewed and sound

These were actively reviewed this pass and hold up — recording them so the audit's coverage is auditable and to avoid re-flagging intentional design:

- **JWT handling** (auth_service.py:227-250): HS256 only; `decode_token()` rejects a mismatched unverified-header `alg` *before* verifying (algorithm-confusion guard), pins `algorithms=[...]`, and checks JTI revocation. JTI revocation is persisted to `auth.json` and re-bootstrapped at startup.
- **Password storage** (auth_service.py:148-153): bcrypt via passlib; no plaintext stored or logged.
- **Path traversal** (file_service.py:195-215, routers/brain.py:38-53, routers/notes.py:65+): all reject empty/`.`/`..` segments, enforce a character allowlist and `.md`-only, and confirm containment with `.resolve()` + `.relative_to(base)`. Consistent across all implementations.
- **Prompt injection** (routers/chat.py:32-36, 275-277): brain content wrapped in `<brain_data>` tags with embedded closing-tags escaped; same escaping applied to AI-generated memory before persisting.
- **AI agent write-gating** (agent_service.py:34-70, 2272-2303): default-deny — only tools in the `_RESEARCH_TOOLS`/`_READ_TOOLS` allowlist run without approval; research mode further restricts `active_tools` to the read set; any tool not on the allowlist becomes a `pending_write` requiring explicit user approval. A new tool is write-gated unless deliberately allow-listed.
- **Automation token** (automations_config.py:34-35): `verify_api_token()` uses `secrets.compare_digest()` (timing-safe); token is 32-byte `token_urlsafe`, auto-generated once and rotatable.
- **File uploads** (routers/assets.py:904-926, assets_service.py:32+): `content_type` validated against an explicit MIME allowlist; on-disk filenames are UUID-based, never derived from user input; 10 MB cap.
- **Rate limiter** (rate_limiter.py:21-33): `X-Forwarded-For` is trusted only when `TRUST_PROXY_HEADERS=true`, which defaults false — IP spoofing can't bypass limits on a directly-exposed instance.
- **User-data read endpoints** (auth_service.py:194-198, routers/auth.py:477-482): password hashes and other sensitive fields are stripped via field allowlists on every user-listing path — no `hashed_password` leakage.
- **Module authorization** (features_service.py:123-145): `get_effective_disabled()` resolves role-disabled ∪ user-disabled correctly for both the legacy flat-list and the workspace-keyed-dict forms; backend `ALL_MODULE_IDS` matches the frontend registry exactly (the pre-check "module mismatch" FAIL is a false positive — its backend grep pattern didn't locate the constant).
- **Endpoint guards**: every endpoint sampled across ~16 routers (tasks, journal, profile, features, push, team, update, brain, assets, auth, contacts automation, calendar, priorities, finance, infisical) carries an appropriate `Depends(get_current_user / require_module / require_pool_edit / require_admin / _require_automation_token)`. No unguarded data endpoint found.
- **Cookie flags** (routers/auth.py:59-67): `httponly=True`, `secure=effective_cookie_secure()`, `samesite="lax"`. (Lax, not strict, is intentional per diagnose.md's false-positive list.)
- **No bare `assert`** in `push_service.py` (diagnose.md checks this for VAPID).

---

## Recommended Remediation Order

1. **B/CRITICAL** — constrain the Docker socket (socket-proxy or privileged broker); it's the one issue where a single app bug becomes host root.
2. **A2/HIGH** — remove or pool-restrict the `GET /automation/assets` bulk export so a leaked automation token can't dump every user's assets (align with the Contacts write-only design).
3. **A/HIGH** — add the rate limit to `POST /auth/token` (one-line fix, closes a live brute-force path).
4. **B/HIGH** — scope the Infisical→`n8n.env` fan-out to an allow-list; set/require strong n8n keys and bind its port to loopback; bump `python-jose` and `python-multipart`.
4. **A/MEDIUM + B/MEDIUM** — add CSP/HSTS, harden startup to fail-closed on the default `SECRET_KEY`, flip the insecure installer defaults, pin third-party images, encrypt backups.
5. **LOW** — supply-chain/dev-tooling hygiene on the next maintenance pass.
