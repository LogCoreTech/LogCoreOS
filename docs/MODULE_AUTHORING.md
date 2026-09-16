# Module Authoring Guide

How to add a new module to LogCoreOS today, post Mod-Store-conversion. Every
module — Journal, Home Assistant, Automations, Calendar, Tasks, Household,
Team, Chat, Notes, Dashboards, Assets, Contacts, Finance, Goals — is a
self-contained `module_packages/<id>/` package with a backend `manifest.py`
and a frontend `manifest.js`, discovered dynamically at boot/build time.
**Nothing is hardcoded** — there is no `ALL_MODULES` list to edit, no router
to register in `main.py`, no route to add to `App.jsx`. This replaces the old
9-step "Adding a New Module" checklist in `docs/AGENTS.md`, which described
the pre-conversion flat `routers/`/`services/` layout and no longer applies.

Primary worked example throughout: **Goals**
(`app/backend/module_packages/goals/`, `app/frontend/src/module_packages/goals/`)
— the newest module, built clean from day one rather than mechanically moved
from a flat file. Also referenced: Contacts and Finance manifests, for
variation on optional fields.

---

## 1. Minimum required structure

```
app/backend/module_packages/<id>/
├── __init__.py                  # empty
├── manifest.py                  # MODULE = ModuleManifest(...) — the contract
└── backend/
    ├── __init__.py              # empty
    └── router.py                # FastAPI router — this IS the module

app/frontend/src/module_packages/<id>/
├── manifest.js                  # default export — the contract
└── frontend/
    └── <Page>.jsx                # the module's main page component
```

Everything else (`service.py`, `dashboard_block.py`, `agent_tools.py`,
`trash_handlers.py`, `tests/`, extra frontend components) is added as needed.
Goals' full backend layout, for reference:

```
module_packages/goals/
├── __init__.py
├── manifest.py
├── backend/
│   ├── __init__.py
│   ├── router.py            # endpoints
│   ├── service.py           # business logic, file I/O
│   ├── dashboard_block.py   # optional — registers a BlockSpec
│   ├── agent_tools.py       # optional — AI tool schemas + execute()
│   └── trash_handlers.py    # optional — only if owned_trash_types is set
└── tests/
    ├── test_goals_router.py
    ├── test_goals_service.py
    ├── test_goals_agent_tools.py
    └── test_goals_trash_handlers.py
```

Backend discovery (`module_registry.py`'s `discover_manifests()`) scans
`module_packages/*/manifest.py` alphabetically, imports each via
`importlib`, and requires `MODULE.id` to equal the directory name — a
mismatch excludes the module with an error, never crashes boot. Frontend
discovery (`app/frontend/src/lib/moduleRegistry.js`) uses
`import.meta.glob('/src/module_packages/*/manifest.js', { eager: true })` —
also Vite build-time, also zero manual registration. **Presence** in
`module_packages/` means "shipped in this build"; **installed/active** is a
separate runtime state (`services/mod_store_service.py`, `installed_modules.json`)
that a module's own migration typically sets (see §4).

---

## 2. The `ModuleManifest` contract

Defined in `app/backend/module_registry.py`. Required fields have no
default; everything else defaults to empty/None/False and can be omitted.

| Field | Required | Purpose |
|---|---|---|
| `id` | yes | Must match the directory name exactly. |
| `display_name` | yes | Human label (Mod Store UI, admin screens). |
| `description` | yes | One-line description (Mod Store UI). |
| `icon` | yes | Emoji, must match the frontend nav icon and `help_section["icon"]`. |
| `version` | yes | Semver string, e.g. `"1.0.0"`. |
| `router_prefix` | yes | Mount path, e.g. `"/api/v1/goals"`. |
| `router_tags` | yes | OpenAPI tags list (can be `[]`). |
| `get_router` | yes | Zero-arg callable returning one `APIRouter`. Lazily imports the real router module (see §3 for why). |
| `owned_brain_paths` | no | List of top-level Brain folder names this module owns (e.g. `["Goals"]`) — hidden from generic Brain browsing/AI access for a user who has this module disabled. Omit if the module has no markdown/file content of its own (e.g. Finance/Contacts/Dashboards/Assets are pure JSON — they still get added to `_ALWAYS_SKIP`/`_brain_skip()` in core for documentation honesty, see their manifest docstrings). |
| `owned_agent_tools` | no | Every AI tool name this module owns, full stop — feeds nothing by itself beyond documentation, but should list every schema returned by `agent_tools.py`. |
| `read_only_agent_tools` | no | Subset of the above that are genuinely read-only. Unions across active modules into `read_only_agent_tool_names()`, which `agent_service.py` uses to allow these tools in research mode / without approval. **A tool not listed here is write-gated by default even if you meant it as read-only** — this is an opt-in allowlist, not a filter. |
| `admin_agent_tools` | no | Subset offered to the model only when the caller is an admin (schema-level gating only — the tool's own `execute()` may still need its own finer check). First used by Household's admin-only shared-task tools. Omit if every tool is available to any module-enabled user. |
| `owned_block_types` | no | Dashboard block `type` strings this module registers (e.g. `["goals_progress"]`). Must match the `type` used in both `dashboard_block.py`'s `BlockSpec` and `manifest.js`'s `blocks[].type`. |
| `owned_metric_providers` | no | List of `MetricProviderSpec` — see §6. Only relevant if another module (typically Goals) should be able to pull a live number from yours. |
| `owned_search_providers` | no | List of `SearchProviderSpec` — see §7. Only relevant if your records should be findable from the global search bar. |
| `owned_trash_types` | no | Record-type strings this module can soft-delete/restore (e.g. `["goal"]`). Requires a `trash_handlers.py` — see §5. |
| `migrations` | no | List of `(name, fn)` tuples, `name` namespaced as `"<module_id>:<fn_name>"`. See §4. |
| `uninstallable` | no (default `False`) | `True` only for a module the app cannot run without (currently Tasks, Chat, Dashboards). A locked module's router registration failure crashes boot loudly instead of being skipped. **A new module should almost never set this.** |
| `on_install` | no | `Callable[[Path], None]` run once when the module is installed (not on every boot) — e.g. Journal's `_on_install` backfills a `Journal/` folder for every existing user. Most new modules don't need this if their data folder is created lazily on first write. |
| `on_new_user` | no | `Callable[[Path, str], None]` run for every currently-active module when a new user is provisioned (`routers/setup.py`) — e.g. seeding one example record (`seed_goal`, `seed_contact`, `seed_finance_book`) prefixed `"Example: "`. |
| `help_section` | no | Dict rendered into the in-app Help section: `{id, icon, title, blurb, howto: [...], tips: [...], modules: [<id>]}`. Every real module ships one — see Goals' or Contacts' manifest for the shape and tone (concrete, feature-by-feature bullets, not marketing copy). Per the release checklist, a `whats_new` entry in `help.json` is a separate, additional step at release time — this `help_section` is the persistent Help-page content. |

`MetricProviderSpec` and `SearchProviderSpec` are separate dataclasses
(also in `module_registry.py`) — see §6/§7.

### Fields you will almost always set
`id`, `display_name`, `description`, `icon`, `version`, `router_prefix`,
`router_tags`, `get_router`, `help_section`. Realistically also
`owned_brain_paths` (if you write markdown/files) and `owned_agent_tools`
+ `read_only_agent_tools` (if you want an AI tool at all).

### Fields you'll skip unless you need them
`admin_agent_tools`, `owned_block_types`, `owned_metric_providers`,
`owned_search_providers`, `owned_trash_types`, `on_install`, `uninstallable`.
Contacts and Finance, both large modules, declare **no** `admin_agent_tools`
at all — it's fine to have zero admin-only tools.

---

## 3. `manifest.py` — worked example (Goals, trimmed)

```python
from pathlib import Path
from module_registry import ModuleManifest, SearchProviderSpec, search_match

def _get_router():
    # Lazy import — keeps manifest.py importable even if router.py (or
    # something it transitively imports) is broken, and avoids import-order
    # issues since discover_manifests() imports every manifest.py eagerly.
    from module_packages.goals.backend.router import router
    return router

def _search_goals(query, tags, user, workspace) -> list[dict]:
    from module_packages.goals.backend import service as goals_service
    results = []
    for g in goals_service.list_goals(user["name"], workspace):
        haystack = " ".join(filter(None, [g.get("title"), g.get("notes"), g.get("category")]))
        if not search_match(query, tags, haystack, g.get("tags") or []):
            continue
        results.append({"title": g["title"], "snippet": g.get("notes"),
                         "tags": g.get("tags") or [], "record_id": g["id"]})
    return results

def m031_migrate_goals(brain: Path) -> None:
    ...  # see §4

def _on_new_user(brain: Path, user_name: str) -> None:
    from services.seed_data_service import seed_goal
    seed_goal(user_name)

MODULE = ModuleManifest(
    id="goals",
    display_name="Goals",
    description="Bigger outcomes broken into subgoals and linked tasks, with an optional live metric to track real progress.",
    icon="🎯",
    version="1.0.0",
    router_prefix="/api/v1/goals",
    router_tags=["goals"],
    get_router=_get_router,
    on_new_user=_on_new_user,
    owned_brain_paths=["Goals"],
    owned_agent_tools=["list_goals", "get_goal", "create_goal", "update_goal",
                        "delete_goal", "link_task_to_goal", "unlink_task_from_goal"],
    read_only_agent_tools=["list_goals", "get_goal"],
    owned_block_types=["goals_progress"],
    owned_trash_types=["goal"],
    owned_search_providers=[SearchProviderSpec(key="goals", label="Goals", resolve=_search_goals)],
    migrations=[("goals:m031_migrate_goals", m031_migrate_goals)],
    help_section={ ... },
)
```

Two conventions worth copying exactly:
- `_get_router()`, `_search_*()`, and any migration function are **module-
  level private functions above `MODULE = ...`**, not inlined lambdas — the
  manifest reads as one declarative block at the bottom of the file.
- The manifest's own **module docstring** is where the design rationale and
  "stays core" decisions live (see §8) — every real manifest in this repo
  opens with a substantial docstring, not just `MODULE = ...`. Future-you
  (or the next engineer) reads this docstring before touching the module.

---

## 4. Migrations: the `mNNN_*` guarded-upgrade idiom

Every module's migrations run **from `migrations.py`'s `_module_migrations()`
at every boot**, regardless of install state — this is how a locked module
gets marked installed in the first place, and how an *optional* new module's
own migration can safely backfill/upgrade existing instances once, ever.

Naming: `"<module_id>:<function_name>"`, e.g. `"goals:m031_migrate_goals"`.
The number is **global and sequential across the whole app**, not per-module
— check `app/backend/migrations/runner.py`'s `MIGRATIONS` list plus every
existing `module_packages/*/manifest.py` for the current highest `mNNN` and
take the next number (Goals used m031; Contacts/Finance used m029/m030).
`module_registry.py`'s `_check_migration_collisions()` excludes your whole
module at boot if the name collides with core's or another module's —
cheap insurance, not a normal failure mode to design around.

Completion is tracked in `brain/_system/migrations.json` — a migration
function runs **exactly once ever**, so it must be written as a one-time
transform, not an idempotent-every-boot check.

Two real shapes exist, pick based on whether your module ships with a
default-on or default-off install state:

**Shape A — existence-guarded backfill** (Contacts' `m029`, Finance's `m030`):
for a module that existed as a hardcoded feature *before* Mod Store, mark it
installed for every pre-existing instance, but let a genuinely fresh install
start with it NOT installed:
```python
def m029_backfill_contacts_installed_from_existing_data(brain: Path) -> None:
    features_file = brain / "_system" / "features.json"
    if not features_file.exists():
        return  # fresh instance — correctly starts uninstalled
    from services import mod_store_service
    from services.file_service import brain_path
    if brain != brain_path():
        return  # test/alternate brain root
    mod_store_service.mark_installed("contacts", by="migration:m029")
```

**Shape B — unconditional install + data conversion** (Goals' `m031`): for a
brand-new module joining the *default* fresh-install baseline, install it on
every instance (fresh or upgrading) unconditionally, and do any one-time data
conversion in the same pass:
```python
def m031_migrate_goals(brain: Path) -> None:
    from services.file_service import brain_path
    if brain != brain_path():
        return
    from services import mod_store_service
    mod_store_service.mark_installed("goals", by="migration:m031")
    # ... then convert/move any legacy data into this module's own storage
```

Both shapes share the `if brain != brain_path(): return` guard — migrations
can run against a test/alternate brain root, and file_service's cached
helpers (`goals_path()`, etc.) always resolve against the *live* brain, so a
migration touching anything beyond raw `brain`-relative paths must bail out
on a non-live root rather than silently touching production data during a
test run.

If your new module has **no legacy data to convert and should simply start
available** (the common case), you likely still want a migration whose only
job is `mark_installed(...)` (Shape B without the data-conversion part) —
there is no other mechanism that marks a module installed on upgrade.

---

## 5. Trash integration (optional)

Only needed if your module supports soft-delete/restore. Declare
`owned_trash_types=["your_record_type"]` on the manifest, then add
`backend/trash_handlers.py` implementing this exact contract (from Goals'):

```python
RECORD_TYPES = ["goal"]

def describe(record_type: str, payload: dict | None) -> tuple[str, str]:
    """(title, module_display_name) for the trash list UI."""
    goal = payload or {}
    return goal.get("title") or "Untitled goal", "Goals"

def restore(store_user: str, workspace: str, entry: dict) -> dict:
    """Re-insert entry['payload'] back into live storage. Raise ValueError
    for a real, user-facing restore failure (e.g. id already exists)."""
    ...

def access_check(user: dict, workspace: str, entry: dict) -> bool:
    """Whether `user` may see/restore this trash entry. list_trash_for_user()
    only surfaces entries from stores the caller can already see, so this is
    often just `return True` unless your module has finer per-item ACLs."""
    ...
```

`module_registry.py`'s `trash_dispatch()` builds `{record_type: (module_id,
handlers)}` for every active module — `services/trash_service.py` never
imports any `module_packages/*` directly. A `trash_handlers.py` that fails
to import degrades to `TrashModuleUnavailable` on restore, not a crash.

---

## 6. AI agent tools (optional)

`backend/agent_tools.py` exports `TOOL_SCHEMAS` (Anthropic tool-use schema
dicts) and `execute(name, inputs, user, workspace)`. Goals' file is a clean
minimal example — 7 tools, `list_goals`/`get_goal` marked read-only:

```python
TOOL_SCHEMAS = [
    {"name": "list_goals", "description": "...", "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "create_goal", "description": "...", "input_schema": {
        "type": "object",
        "properties": {"title": {"type": "string"}, "parent_id": {"type": "string", "description": "Optional — makes this a subgoal"}},
        "required": ["title"],
    }},
    ...
]

def execute(name: str, inputs: dict, user: dict, workspace: str = "personal"):
    if name == "list_goals":
        return goals_service.list_goals(user["name"], workspace)
    if name == "create_goal":
        ...
    return None
```

Then on the manifest:
- **Every** tool name goes in `owned_agent_tools`.
- Tools with **no side effects, safe to run without approval and in
  research mode** go in `read_only_agent_tools` too (e.g. `list_goals`,
  `get_goal`). Anything not listed here is write-gated by default —
  requires the user's approve-mode confirmation — even a tool you consider
  harmless. This is an intentional opt-in default established across every
  conversion.
- Tools that should only ever be **offered to admins** go in
  `admin_agent_tools` (schema-level filtering in `agent_service.py`'s
  `_get_tools()` only — your `execute()` should still enforce its own
  finer-grained check if the action needs one, the same way Household's
  `complete_shared_task` re-checks admin-or-assignee on top of the schema
  gate). Most modules declare none — Contacts and Finance both ship zero
  admin-only tools.

---

## 7. Dashboard block (optional)

Two halves, backend + frontend, both keyed by the same `type` string.

**Backend** — `backend/dashboard_block.py` registers a `BlockSpec`
(`services/dashboard_blocks/registry.py`):
```python
from services.dashboard_blocks.registry import (
    BlockRenderCtx, BlockRenderResult, BlockSpec, register, scoped_target,
)

def resolve_goals_progress(ctx: BlockRenderCtx) -> BlockRenderResult:
    target = scoped_target(ctx)
    if target is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    roots = goals_service.get_root_goals(target, ctx.workspace)
    ...
    return BlockRenderResult(ok=True, data={"goals": goals})

register(BlockSpec(
    type="goals_progress",
    label="Goals Progress",
    category="live_aggregate",       # | "record_linked" | "freeform"
    resolver=resolve_goals_progress,
    scope_configurable=True,
    module="goals",                  # feeds module-disabled gating
))
```
`BlockSpec` also has `admin_only: bool`, `workspace: str | None` (None =
both), and `record_ref_fields: dict[str, str]` (e.g. `{"asset_id":
"assets"}`) for a block that links to another module's record — omit
whichever you don't need.

**Frontend** — declare the block in `manifest.js`'s `blocks` array:
```js
export default {
  id: 'goals',
  to: '/goals',
  icon: '🎯',
  label: 'Goals',
  recordParam: 'goal',
  loadPage: () => import('./frontend/Goals.jsx'),
  blocks: [
    {
      type: 'goals_progress',            // must match BlockSpec.type exactly
      loadComponent: () => import('./frontend/GoalsProgressBlock.jsx'),
      icon: '🎯',
      label: 'Goals Progress',
      defaultLayout: { w: 12, h: 9 },     // grid units — see DashboardGrid.jsx
      shape: 'list',                      // 'detail' (default) | 'list' | 'stat'
      // configSchema: [...] — only if the block needs an "edit config" affordance
    },
  ],
}
```
`app/frontend/src/components/dashboard/blockRegistry.js` loops every
`MODULE_PACKAGES` entry's `blocks` array and merges each into
`BLOCK_REGISTRY` with `lazy(loadComponent)` — no hardcoded frontend entry
needed. If a block entry has `configSchema`, it's merged into
`CONFIG_FIELD_SCHEMAS[type]` the same automatic way. The backend
(`GET /dashboards/catalog`) remains the single source of truth for
**gating** (admin_only/workspace/module-disabled) — the frontend registry
only supplies icon/component/default size.

---

## 8. Metric provider (optional — only if Goals should read your data)

Lets Goals' metric picker pull a live "current vs. target → percent" number
from your module **without Goals containing any module-specific logic** —
declared on *your* manifest, never on Goals'. From Contacts' manifest:
```python
def _resolve_number_field(config: dict, user: dict, workspace: str) -> dict:
    """Must never raise — a broken provider degrades to 0%, never crashes
    Goals' own list/get endpoints."""
    from module_registry import directional_pct
    from services import contacts_service
    ...
    current = (contact.get("custom") or {}).get(config.get("field_key"))
    if not isinstance(current, (int, float)):
        return {"current": 0, "target": config.get("target_value"), "pct": 0}
    pct = directional_pct(current, config.get("target_value"),
                           config.get("direction", "increase"), config.get("start_value"))
    return {"current": current, "target": config.get("target_value"), "pct": pct}

MODULE = ModuleManifest(
    ...,
    owned_metric_providers=[
        MetricProviderSpec(
            key="number_field",             # unique within YOUR module only
            label="Contacts: Number Field",
            config_schema=[                  # same {key,label,kind,...} shape as blockRegistry's CONFIG_FIELD_SCHEMAS
                {"key": "contact_id", "label": "Contact", "kind": "contact", "optional": True},
                {"key": "field_key", "label": "Field", "kind": "contactNumberField"},
                {"key": "target_value", "label": "Target value", "kind": "number"},
            ],
            resolve=_resolve_number_field,
        ),
    ],
)
```
`module_registry.metric_providers()` namespaces the key as
`f"{module_id}:{key}"` and returns every active module's providers — Goals'
`GET /goals/metric-providers` just lists whatever comes back. Use the shared
`module_registry.directional_pct(current, target, direction, start_value)`
helper for the increase/decrease math rather than reimplementing it —
getting "decrease" backwards makes a weight-loss goal show *worse* progress
as the user actually loses weight.

---

## 9. Search provider (optional — makes your records findable globally)

Same generic-registry shape as metric providers, for the global search bar.
```python
def _search_goals(query: str, tags: list[str], user: dict, workspace: str) -> list[dict]:
    """Must never raise. `query` may be empty (tag-only browse); `tags` may
    be empty (plain text search) — search_service.search() never calls a
    provider when both are empty."""
    from module_registry import search_match
    results = []
    for g in goals_service.list_goals(user["name"], workspace):
        haystack = " ".join(filter(None, [g.get("title"), g.get("notes"), g.get("category")]))
        if search_match(query, tags, haystack, g.get("tags") or []):
            results.append({"title": g["title"], "snippet": g.get("notes"),
                             "tags": g.get("tags") or [], "record_id": g["id"]})
    return results

# on MODULE:
owned_search_providers=[SearchProviderSpec(key="goals", label="Goals", resolve=_search_goals)],
```
Use the shared `module_registry.search_match(query, tags, haystack,
own_tags)` for the substring + tag-intersect logic, and
`module_registry.search_snippet(text, query)` if you need a real content
excerpt (not just a title) — same helpers every provider in this codebase
uses rather than reimplementing matching per module.

---

## 10. The "stays core" rule — when NOT to move something into your package

Documented in `docs/MEMORY.md` (2026-08-24 → 2026-08-28 entry), applied
about a dozen times across the 13-module rollout:

> A service/component consumed by something OTHER than its own module's
> frontend/backend — a sibling module's router, a scheduler job, a core
> migration — stays core, doesn't move with the rest of the module.

Concretely, before you move (or, for a new module, decide where to put) a
service function, grep for every caller. If any caller is:
- **A sibling module's router or service** (e.g. `dashboard`'s router calls
  `contacts_service` directly for its Hero block subject resolver;
  `chat`'s router calls it for AI system-prompt profile context) — stays
  core.
- **A `scheduler.py` cron job** imported directly at boot, regardless of
  any module's install state (e.g. `n8n_service.py`, `finance_planning_service.py`,
  `simplefin_service.py`) — stays core. A scheduler dependency counts
  exactly like a sibling-module dependency for this rule, not a weaker one.
- **A core migration** in `migrations/runner.py`, which runs before module
  registration exists at all in boot order (e.g. `dashboards_service.py`)
  — stays core.
- **`services/user_deletion_service.py`** for the four sharing-capable
  stores (assets/finance/contacts/notes) — stays core.

If, on the other hand, **nothing outside your own package needs it** — the
Goals case exactly (`module_packages/goals/backend/service.py` has zero
external callers; Goals doesn't even use the per-user share-handshake
pattern Assets/Finance/Contacts/Notes need, so `user_deletion_service.py`
needed no Goals-specific code at all) — it belongs entirely inside
`module_packages/<id>/backend/`, full stop.

One more nuance worth knowing before you design a pool (household/team)
variant of your feature: a dashboard block or router endpoint that serves
*pool* data should usually be **gated on the pool module (`household`/
`team`), not on your module** — e.g. `household_goals`/`team_goals`
dashboard blocks live in `household`'s/`team`'s own `dashboard_block.py`,
gated `module="household"`/`module="team"`, not `module="goals"` — this
mirrors `household_tasks`/`team_tasks`'s established precedent (gate pool
visibility on pool membership, not on the underlying data-owning module).
The pool *router* endpoints themselves, though, typically live in your
OWN module's router (the "one owning module serves personal + pool" shape
Finance/Contacts/Assets/Goals all use) so that pool-feature availability
ties to your module's own install state, not a sibling's.

---

## 11. Ordered checklist

1. **Scope it through a real interview, not a mechanical template** — Goals
   was "genuinely new," not a conversion; know what data model, sharing
   model, and pool behavior you actually need before writing files.
2. Pick the module `id` (short, lowercase, matches the directory name
   exactly) and check `migrations/runner.py` + every `module_packages/*/manifest.py`
   for the next free `mNNN` number.
3. Create `app/backend/module_packages/<id>/{__init__.py, manifest.py, backend/__init__.py, backend/router.py}`.
4. Write `backend/service.py` (business logic, file I/O against
   `brain/USERS/<user>/<YourFolder>/...json` via `services/file_service.py`
   helpers) — keep it entirely inside the package unless §10 says otherwise.
5. Wire `router.py`'s endpoints behind `require_module("<id>")`
   (`routers/auth.py`), and `require_pool_edit`/an inline pool-write check
   if you support household/team pool data.
6. Write `manifest.py`: required fields first (§2), a migration that at
   minimum `mark_installed()`s your module (§4), and a `help_section`.
   Write the module docstring — rationale, "stays core" calls you made,
   anything a future reader needs (§3).
7. Add `app/frontend/src/module_packages/<id>/{manifest.js, frontend/<Page>.jsx}`.
   `manifest.js` needs at minimum `id`, `to`, `icon`, `label`, `loadPage`;
   add `recordParam` if the page deep-links to a specific record.
8. Add an API client (`frontend/api.js`) built on the shared `get/post/patch/del`
   helpers from `lib/api.js` — never a raw `fetch()` reimplementation.
9. If applicable: `backend/dashboard_block.py` + a `blocks[]` entry in
   `manifest.js` (§7); `backend/agent_tools.py` + `owned_agent_tools`/
   `read_only_agent_tools`/`admin_agent_tools` (§6); `backend/trash_handlers.py`
   + `owned_trash_types` (§5); a `MetricProviderSpec` (§8) or
   `SearchProviderSpec` (§9) if another module or global search should see
   your data.
10. Write tests under `module_packages/<id>/tests/` — router tests call
    endpoint functions directly with a pre-resolved user dict + workspace
    string (see `test_goals_router.py`'s own docstring for the convention),
    matching `test_contacts_router.py`/`test_assets_router.py`.
11. Confirm zero edits were needed to `main.py`, `App.jsx`,
    `lib/constants.js`, or `lib/moduleRegistry.js` — if you touched any of
    those, something in discovery isn't wired right.
12. Run the migration locally (boot the app once) and confirm
    `GET /mod-store/installed` and `GET /mod-store/active` both show your
    module id.
13. Add the release checklist's `whats_new` entry in `help.json` (Help
    section + notification + banner) before shipping — see
    `docs/MEMORY.md`'s release-checklist note; this is a separate step from
    the manifest's own `help_section`.
