"""Demo-instance nightly reset.

Wipes every non-admin user's Brain folder and auth.json entry, so a public
demo (app.logcoretech.com) starts each day clean. Never touches admin
accounts, or the _template/_household/_team pseudo-user folders (shared
pool storage, not per-visitor data).

Run inside the app container, not on the host — it imports the same
services the API uses:

    docker compose exec -T app python3 demo_reset.py

Wire into a demo host via cron:

    0 3 * * * cd /path/to/logcoreos && docker compose exec -T app python3 demo_reset.py >> /var/log/logcore-demo-reset.log 2>&1

SAFETY GATE: refuses to do anything unless DEMO_MODE=true is set for this
instance. This is deliberate — the failure mode for a destructive nightly
script being wired onto the wrong instance (e.g. a cron entry copy-pasted
onto a personal/family install) is silent, unrecoverable data loss. Requiring
an explicit, documented, instance-level opt-in means that mistake no-ops
instead of deleting real users' data.
"""

import shutil

from config import settings
from services import auth_service
from services.file_service import brain_path

_PRESERVED_FOLDERS = {"_template", "_household", "_team"}


def main() -> None:
    if not settings.demo_mode:
        print(
            "REFUSING: DEMO_MODE is not set to true on this instance. "
            "This script deletes non-admin user data and must never run "
            "against a personal/managed instance. Set DEMO_MODE=true in "
            "docker/.env only on a genuine public demo deployment."
        )
        return

    data = auth_service._load_auth()
    users = data.get("users", [])

    kept = [u for u in users if u.get("role") == "admin"]
    removed = [u for u in users if u.get("role") != "admin"]

    if not kept:
        print("REFUSING: no admin account found on this instance — would lock it out of itself.")
        return

    kept_names = {u["name"] for u in kept}
    users_dir = brain_path() / "USERS"
    deleted_folders = 0
    if users_dir.exists():
        for entry in sorted(users_dir.iterdir()):
            if not entry.is_dir() or entry.name in _PRESERVED_FOLDERS or entry.name in kept_names:
                continue
            shutil.rmtree(entry, ignore_errors=True)
            deleted_folders += 1

    data["users"] = kept
    auth_service._save_auth(data)

    print(
        f"Demo reset: kept {len(kept)} admin account(s), removed {len(removed)} "
        f"user(s), deleted {deleted_folders} Brain folder(s)."
    )


if __name__ == "__main__":
    main()
