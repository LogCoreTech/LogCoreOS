# LogCore OS

A self-hosted, values-driven family life operating system with an AI that knows you personally.

---

## Two Products

**LogCore Brain** (`brain/`) — Free, open source. Markdown + JSON files. Works with any AI — Claude Code, GPT, Ollama, anything. Take your Brain folder anywhere, and your AI context comes with you.

**LogCore App** (`app/`) — The software layer. Python FastAPI backend + React frontend, installable as a PWA on phones and desktops. Dashboards, task management, integrated AI chat, background scheduling, push notifications. This is what you run (or pay to have hosted).

---

## Quick Start

### Prerequisites
Install these before running the launch script:

| Tool | Version | Install |
|---|---|---|
| Docker | latest | [docs.docker.com/engine/install](https://docs.docker.com/engine/install/) |
| Docker Compose plugin (v2) | latest | [docs.docker.com/compose/install](https://docs.docker.com/compose/install/) |
| Node.js | 20+ | [nodejs.org](https://nodejs.org/en/download/) or [nvm](https://github.com/nvm-sh/nvm) |
| curl | any | `sudo apt-get install curl` |

### Launch

```bash
git clone <repo-url>
cd LogCoreOS
./launch.sh
```

That's it. The script handles everything else:
- Generates a secure `SECRET_KEY` automatically
- Builds the React frontend
- Starts all Docker containers
- Waits for the app to become healthy

### First login
Open `http://localhost:8000` in your browser. The first user to register becomes the admin.

After logging in, go to **Admin → AI Settings** to add your Anthropic API key (needed for AI chat).

### Tunnel / external access
If you're exposing the app via Cloudflare Tunnel, ngrok, or a reverse proxy, go to **Admin → Hosting** after first login, select "HTTPS via Tunnel", and enter your domain URL. No restart needed.

On your phone: open Chrome → go to your app URL → tap "Add to Home Screen" to install as a PWA.

### Re-running the script
```bash
./launch.sh              # rebuild frontend + restart containers
./launch.sh --skip-build # restart only (skip npm build if nothing changed)
./launch.sh --reconfigure # reset docker/.env and start fresh
```

---

## Architecture

```
brain/               ← The Brain (free, portable, AI-readable)
  AGENTS.md          ← AI boot protocol
  SOUL.md            ← AI personality
  USERS/
    _template/       ← Template copied for each new user
    {User Name}/     ← Created by the setup wizard on first login
      Profile.md
      Long_Term_Memory.md
      Short_Term_Memory.md
      Tasks/
        tasks.json
        tasks_history.json
        tasks_view.md
  skills/
    life-priorities/ ← Task scoring + recurring logic

app/
  backend/           ← Python FastAPI (reads/writes brain/ files)
  frontend/          ← React + Vite + Tailwind (PWA)

docker/
  docker-compose.yml
  .env.example
```

---

## Using the Brain Without the App

The Brain files work with any AI out of the box. To use with Claude Code:

1. Open Claude Code in this directory
2. The AI reads `brain/AGENTS.md` and follows its boot protocol
3. Tell it which user you are and it loads your personal context
4. Chat naturally — it knows your priorities, tasks, and context

---

## Notifications (ntfy)

The app sends push notifications via [ntfy](https://ntfy.sh) (self-hosted, free).

1. Install the ntfy app on your phone (Android or iOS)
2. Add your server: `http://YOUR_SERVER_IP:5680`
3. Subscribe to your personal channel — find it in **Settings → Notifications** after logging in
4. Your channel ID is randomly generated at registration for privacy

---

## License

Brain files: MIT (free, open source, share freely)
App: TBD
