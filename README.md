# LogCore OS

A self-hosted, values-driven family life operating system with an AI that knows you personally.

---

## Two Products

**LogCore Brain** (`brain/`) — Free, open source. Markdown + JSON files. Works with any AI — Claude Code, GPT, Ollama, anything. Take your Brain folder anywhere, and your AI context comes with you.

**LogCore App** (`app/`) — The software layer. Python FastAPI backend + React frontend, installable as a PWA on phones and desktops. Dashboards, task management, integrated AI chat, background scheduling, push notifications. This is what you run (or pay to have hosted).

---

## Quick Start

### Requirements
- Docker + Docker Compose
- Node.js 20+ (to build the frontend)
- An Anthropic API key (for AI chat — optional but recommended)

### 1. Build the frontend
```bash
cd app/frontend
npm install
npm run build
```

### 2. Configure environment
```bash
cp docker/.env.example docker/.env
# Edit docker/.env and fill in SECRET_KEY and ANTHROPIC_API_KEY
```

Generate a secret key:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Start the stack
```bash
cd docker
docker compose up -d
```

### 4. Open the app
Go to `http://localhost:8000` in your browser.

On your phone: open Chrome → go to `http://YOUR_SERVER_IP:8000` → tap "Add to Home Screen" to install as a PWA.

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
3. Subscribe to your channel: `logcore-{your-name}` (e.g., `logcore-anthony`)
4. Configure your channel name in the app Settings

---

## License

Brain files: MIT (free, open source, share freely)
App: TBD
