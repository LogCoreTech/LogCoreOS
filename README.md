# LogCore OS

[![CI](https://github.com/LogCoreTech/LogCoreOS/actions/workflows/ci.yml/badge.svg)](https://github.com/LogCoreTech/LogCoreOS/actions/workflows/ci.yml)

A self-hosted life operating system for individuals, families, and households. An AI that knows you personally — your priorities, your goals, your people — running privately on your own server.

---

## What it does

LogCore OS gives you a private command centre for your life:

- **AI chat** with full personal context — your priorities, tasks, and memory are injected automatically
- **Task management** with intelligent scoring based on your life priorities
- **Journal, Notes, and Calendar** — all in one place
- **Household hub** — shared tasks and events across everyone in your home
- **Push notifications** for daily task digests, overdue reminders, and weekly reviews
- **PWA** — installs on your phone and desktop like a native app
- **Multi-user** — one server supports a whole household or small team

All your data lives as readable files on your own server. No third-party cloud. No vendor lock-in.

---

## Self-Hosting

### Linux (recommended for servers)

```bash
git clone https://github.com/LogCoreTech/LogCoreOS.git
cd LogCoreOS
bash launch.sh --install-deps
```

`--install-deps` automatically installs Docker, Node.js, and curl if they are missing, then launches the app. Safe to re-run — nothing is reinstalled if already present.

### macOS / Windows

Install the following first, then run `bash launch.sh`:

| Tool | Version | Install |
|---|---|---|
| Docker | latest | [docs.docker.com/engine/install](https://docs.docker.com/engine/install/) |
| Docker Compose plugin (v2) | latest | [docs.docker.com/compose/install](https://docs.docker.com/compose/install/) |
| Node.js | 20+ | [nodejs.org](https://nodejs.org/en/download/) or [nvm](https://github.com/nvm-sh/nvm) |
| curl | any | `brew install curl` |

### What the launch script does

- Generates a secure `SECRET_KEY` automatically
- Builds the React frontend
- Starts all Docker containers
- Waits for the app to be healthy

### First login

Open `http://localhost:8000` in your browser. The first user to register becomes the admin.

After logging in, go to **Admin → AI Settings** to add your Anthropic API key (required for AI chat).

### External access

If you're exposing the app via Cloudflare Tunnel, ngrok, or a reverse proxy, go to **Admin → Hosting** after first login, select "HTTPS via Tunnel", and enter your domain URL. No restart needed.

To install as a PWA on your phone: open your browser, navigate to your app URL, and tap "Add to Home Screen".

### Script options

```bash
bash launch.sh                  # rebuild frontend + restart containers
bash launch.sh --install-deps   # install any missing deps, then launch
bash launch.sh --skip-build     # restart only (skip npm build if nothing changed)
bash launch.sh --reconfigure    # reset docker/.env and start fresh
```

---

## Managed Hosting

Don't want to run your own server? LogCore OS is available as a fully managed hosted service.

We handle setup, updates, backups, and uptime — you just use the app.

> Hosted plans coming soon. [logcoretech.com](https://logcoretech.com)

---

## Your Data

All your data is stored as Markdown and JSON files in the `brain/` folder on your server. It is human-readable, portable, and not tied to this app.

You can export your Brain at any time from **Admin → Export** as a zip file. The files work with any AI — Claude, GPT, Ollama, or anything else. Your context comes with you wherever you go.

---

## Notifications

Push notifications are handled via [ntfy](https://ntfy.sh) (self-hosted, included in the Docker stack).

1. Install the ntfy app on your phone (Android or iOS)
2. Add your server: `http://YOUR_SERVER_IP:5680`
3. Subscribe to your personal channel — find it in **Settings → Notifications** after logging in

---

## License

AGPL v3 — free to self-host and modify. Any commercial service built on this code must also be published as open source.

See [LICENSE](./LICENSE) for the full terms.
