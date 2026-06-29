# OWNER_SETUP.md — LogCoreTech Business Setup Checklist

> **Temporary working document.** Delete or archive when setup is complete.
> This covers every manual task the LogCoreTech owner must complete before the managed service is production-ready.

---

## 1. Infisical (Secrets Manager)

Infisical replaces `.env` files for managed instances. All secrets live here and are pulled at startup.

- [ ] Create an [Infisical](https://infisical.com) account and organisation (`LogCoreTech`)
- [ ] Create a project (e.g. `logcoreos-prod`) with a `prod` environment
- [ ] Add the following secrets to the `prod` environment:

| Secret key | What it is | How to generate |
|---|---|---|
| `SECRET_KEY` | JWT signing key | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `ANTHROPIC_API_KEY` | AI provider key | From console.anthropic.com |
| `N8N_API_KEY` | n8n REST API key | Any strong random string |
| `N8N_ENCRYPTION_KEY` | n8n credential encryption key | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `WORKFLOWS_BASE_URL` | GitHub raw URL for business workflow JSONs | `https://raw.githubusercontent.com/logcoretech/business-workflows/main` |
| `WORKFLOWS_TOKEN` | GitHub fine-grained PAT for private workflow repo | See step 2 |
| `CLOUDFLARE_TUNNEL_TOKEN` | Tunnel token per instance | See step 4 |

- [ ] Note the `INFISICAL_TOKEN`, `INFISICAL_URL`, `INFISICAL_ENV`, and `INFISICAL_PROJECT_ID` values — these go into each instance's `docker/.env`

---

## 2. Private Workflow Repo (GitHub)

Business workflow JSONs live here. Never committed to the public LogCoreOS repo.

- [ ] Create a **private** GitHub repo: `logcoretech/business-workflows`
- [ ] Generate a **fine-grained Personal Access Token**:
  - Go to GitHub → Settings → Developer settings → Fine-grained tokens
  - Repository access: **Only `logcoretech/business-workflows`**
  - Permissions: **Contents → Read-only** (nothing else)
  - Set a long expiry (1 year) and calendar a reminder to rotate it
- [ ] Add the token to Infisical as `WORKFLOWS_TOKEN`
- [ ] Add the raw base URL to Infisical as `WORKFLOWS_BASE_URL`:
  ```
  https://raw.githubusercontent.com/logcoretech/business-workflows/main
  ```
- [ ] When you have actual n8n workflows to ship:
  - Export each workflow from n8n as JSON
  - Push to `logcoretech/business-workflows/{key}.json`
  - Add a matching stub to `app/backend/automations_stubs/{key}.stub.json`:
    ```json
    { "key": "slack_digest", "name": "Slack Digest", "tags": ["slack", "daily"] }
    ```
  - Ship a new LogCoreOS release — instances auto-sync within 6 hours or on next restart

---

## 3. n8n Security

By default the n8n UI is exposed on port 5678. Decide on an approach before going live.

- [ ] **Recommended:** Remove the port mapping so n8n is internal-only (users only interact via LogCore UI):
  - In `docker/docker-compose.yml`, remove or comment out `ports: - "5678:5678"` under the `n8n` service
  - n8n remains reachable internally at `http://n8n:5678` for the LogCore backend
- [ ] **If you need direct n8n UI access:** Set up n8n owner account on first launch (visit `http://localhost:5678` on the server and complete the setup wizard before removing tunnel access)
- [ ] Ensure `N8N_ENCRYPTION_KEY` is set in Infisical — required for n8n to encrypt stored credentials

---

## 4. Cloudflare Tunnel (Per Instance)

Each managed customer instance needs its own tunnel so it's reachable via a custom subdomain.

- [ ] Create a Cloudflare account and add your domain
- [ ] For each new instance:
  - Go to Cloudflare Zero Trust → Networks → Tunnels → Create tunnel
  - Name it after the customer (e.g. `customer-abc`)
  - Copy the tunnel token
  - Add a public hostname route: `customer-abc.yourdomain.com` → `http://localhost:8000`
  - Add `CLOUDFLARE_TUNNEL_TOKEN=<token>` to the instance's `docker/.env` (or to a per-instance Infisical environment)

---

## 5. First Instance Deployment

Steps to go from a fresh server to a running managed instance.

- [ ] Server requirements: Ubuntu 22.04+, Docker + Docker Compose, Git, 2 GB RAM minimum
- [ ] Clone the repo:
  ```bash
  git clone https://github.com/logcoretech/logcoreos.git
  cd logcoreos
  ```
- [ ] Create `docker/.env` from the example:
  ```bash
  cp docker/.env.example docker/.env
  ```
- [ ] Fill in the Infisical block in `docker/.env` (everything else will be pulled from Infisical at startup):
  ```
  INFISICAL_URL=https://app.infisical.com
  INFISICAL_TOKEN=<machine-identity-token>
  INFISICAL_ENV=prod
  INFISICAL_PROJECT_ID=<optional>
  ```
- [ ] Add the Cloudflare tunnel token for this instance:
  ```
  CLOUDFLARE_TUNNEL_TOKEN=<tunnel-token>
  ```
- [ ] Run the launch script:
  ```bash
  bash launch.sh
  ```
- [ ] Complete the setup wizard at `https://customer.yourdomain.com/setup`
- [ ] Log in as admin → Admin panel → Test AI connection, Test n8n connection

---

## 6. Admin Panel Configuration (Per Instance)

After first launch, configure the instance via the Admin UI.

- [ ] **AI Settings** — verify provider + model are correct (pulled from Infisical, should auto-fill)
- [ ] **Web Search** — add Tavily API key if AI research mode is wanted (free tier: 1,000/month)
- [ ] **Hosting** — set the public domain URL; enable `Cookie Secure` and `Trust Proxy Headers`
- [ ] **n8n** — click Test Connection to verify n8n is reachable; click Sync Workflows Now to pull business workflows for the first time
- [ ] **Infisical** — verify the Infisical card shows as connected
- [ ] **Users** — create user accounts for the customer; assign appropriate feature roles (Personal or Business member)

---

## 7. Feature Roles (One-time, in Admin UI)

Set up the feature roles customers will be assigned to.

- [ ] Log in as admin → Admin → Roles
- [ ] Confirm the built-in `member` role has the right defaults
- [ ] Create a **Business Member** role: all modules on including `automations_business`
- [ ] Create a **Personal Member** role: all modules on except `automations_business` and `journal` (adjust to taste)
- [ ] Assign roles to users as you onboard them

---

## 8. Ongoing Operations

- [ ] **Rotate `WORKFLOWS_TOKEN`** (GitHub PAT) before it expires — update in Infisical, all instances pick it up within 6 hours
- [ ] **Update business workflows**: push new JSON to `logcoretech/business-workflows`, ship a LogCoreOS release with updated stubs → instances auto-sync
- [ ] **Remove a business workflow**: delete the JSON from the private repo AND remove the stub from `app/backend/automations_stubs/` in the same release — instances delete it from n8n on next sync
- [ ] **Brain backups**: `docker/backup.sh` keeps the last 30 backups; set up a cron job to run it nightly
- [ ] **LogCoreOS updates**: `git pull && bash launch.sh` on each instance (or automate with a deploy pipeline)
