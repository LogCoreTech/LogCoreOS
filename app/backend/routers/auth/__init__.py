"""Auth router package.

This used to be a single ~1230-line routers/auth.py. It has been split into
5 files by concern, each with its own `APIRouter()`:

- deps.py            core dependencies every other router imports
                      (get_current_user, get_workspace, require_admin,
                      require_module, require_pool_edit) plus small shared
                      helpers (_COOKIE, _set_auth_cookie, _clear_auth_cookie,
                      _validate_timezone, _VALID_WORKSPACES, _admin_limit).
- session.py          login/logout/register/token/status/demo-login.
- profile.py          self-service /me endpoints (profile, background
                      image, /today).
- admin_users.py      admin user management (create/list/update-role/
                      delete/deletion-preview/deletion-execute/workspaces/
                      pool-edit/workspace-modules).
- admin_settings.py   instance settings (registration/session/workspace
                      settings, search settings, hosting settings,
                      automation token). Infisical settings were never part
                      of this file — they live in their own routers/infisical.py.

`routers.auth` is imported by ~43 other files across the backend (every
router depends on get_current_user/get_workspace/require_admin/
require_module/require_pool_edit; a handful of others reach for
ai_settings_path, _ACCENT_COLOR_RE, or specific request models/endpoint
functions directly, mostly from tests). This __init__ re-exports every name
that used to be a module-level attribute of the flat routers/auth.py, so
every caller that imports a name off this package keeps resolving it
EXACTLY as it did before this split, and main.py's
`app.include_router(auth.router, prefix="/api/v1/auth",
tags=["auth"])` keeps working unchanged since `auth` (the package) still
exposes a single `router` attribute.

The composed `router` below follows the exact same pattern
module_packages/finance/manifest.py's `_get_router()` already established
in this codebase for combining several sub-routers into one
(ModuleManifest.get_router() there has the same "only one router" constraint
this package's caller — main.py's app.include_router() — has): a plain
APIRouter() that nested-include_router()s each sibling's own router, with no
new tag added, so OpenAPI grouping is unchanged.
"""

from fastapi import APIRouter

# Each sibling module also imported directly (not just its names) so
# `router.include_router(_session.router)` etc. below can reach its own
# APIRouter() — isort groups these plain `from . import X as _X` imports
# ahead of the named `from .X import (...)` blocks that follow.
from . import admin_settings as _admin_settings
from . import admin_users as _admin_users
from . import profile as _profile
from . import session as _session

# --- admin_settings.py: instance-wide admin settings --------------------
from .admin_settings import (
    _HOSTING_SETTINGS_PATH,
    AdminSettingsRequest,
    HostingSettingsRequest,
    SearchSettingsRequest,
    _automation_token_limit,
    ai_settings_path,
    apply_hosting_settings,
    get_admin_settings,
    get_automation_token,
    get_hosting_settings,
    get_search_settings,
    rotate_automation_token,
    update_admin_settings,
    update_search_settings,
)
from .admin_users import (
    _ADMIN_USER_FIELDS,
    _VALID_POOLS,
    CreateUserRequest,
    DeletionDecision,
    DeletionExecuteRequest,
    ModuleAccessRequest,
    PoolEditRequest,
    RoleUpdateRequest,
    UpdateRoleRequest,
    UserUpdateRequest,
    WorkspaceModulesRequest,
    WorkspacesRequest,
    _all_module_ids,
    admin_create_user,
    admin_delete_user,
    admin_list_users,
    admin_update_user_role,
    admin_user_deletion_execute,
    admin_user_deletion_preview,
    list_users_legacy,
    update_user_by_admin,
    update_user_modules,
    update_user_pool_edit,
    update_user_role_legacy,
    update_user_workspaces,
    update_workspace_modules,
)

# --- deps.py: core dependencies + shared helpers -------------------------
from .deps import (
    _COOKIE,
    _VALID_WORKSPACES,
    _admin_limit,
    _clear_auth_cookie,
    _set_auth_cookie,
    _validate_timezone,
    bearer_optional,
    get_current_user,
    get_workspace,
    logger,
    require_admin,
    require_module,
    require_pool_edit,
)

# --- profile.py: self-service /me endpoints -------------------------------
from .profile import (
    _ACCENT_COLOR_RE,
    _ALLOWED_BG_TYPES,
    _BG_MAX_BYTES,
    _VALID_CORNER_STYLES,
    _VALID_DARK_MODES,
    _VALID_DENSITIES,
    _VALID_GRADIENT_IDS,
    _VALID_SHORTCUT_WORKSPACES,
    _VALID_TASKS_FILTERS,
    _VALID_TASKS_SORT_MODES,
    MeUpdateRequest,
    _find_user_background,
    _get_me_limit,
    _me_limit,
    _validate_accent_color,
    _validate_background,
    _validate_corner_style,
    _validate_dark_mode,
    _validate_density,
    _validate_tasks_filter,
    _validate_tasks_sort_mode,
    delete_background,
    get_background,
    get_today,
    me,
    update_me,
    upload_background,
)

# --- session.py: login/logout/register/token/status/demo-login -----------
from .session import (
    _DEMO_ADJECTIVES,
    _DEMO_NOUNS,
    _DEMO_PRIORITIES,
    DemoLoginRequest,
    LoginRequest,
    RegisterRequest,
    _demo_login_limit,
    _login_limit,
    _register_limit,
    _status_limit,
    demo_login,
    get_token,
    login,
    logout,
    register,
    registration_status,
)

# --- assemble the single router main.py mounts --------------------------
router = APIRouter()
router.include_router(_session.router)
router.include_router(_profile.router)
router.include_router(_admin_users.router)
router.include_router(_admin_settings.router)

__all__ = [
    "router",
    # deps
    "_admin_limit",
    "_clear_auth_cookie",
    "_COOKIE",
    "_set_auth_cookie",
    "_validate_timezone",
    "_VALID_WORKSPACES",
    "bearer_optional",
    "get_current_user",
    "get_workspace",
    "logger",
    "require_admin",
    "require_module",
    "require_pool_edit",
    # session
    "_DEMO_ADJECTIVES",
    "_DEMO_NOUNS",
    "_DEMO_PRIORITIES",
    "_demo_login_limit",
    "_login_limit",
    "_register_limit",
    "_status_limit",
    "DemoLoginRequest",
    "LoginRequest",
    "RegisterRequest",
    "demo_login",
    "get_token",
    "login",
    "logout",
    "register",
    "registration_status",
    # profile
    "_ACCENT_COLOR_RE",
    "_ALLOWED_BG_TYPES",
    "_BG_MAX_BYTES",
    "_find_user_background",
    "_get_me_limit",
    "_me_limit",
    "_validate_accent_color",
    "_validate_background",
    "_validate_corner_style",
    "_validate_dark_mode",
    "_validate_density",
    "_validate_tasks_filter",
    "_validate_tasks_sort_mode",
    "_VALID_CORNER_STYLES",
    "_VALID_DARK_MODES",
    "_VALID_DENSITIES",
    "_VALID_GRADIENT_IDS",
    "_VALID_SHORTCUT_WORKSPACES",
    "_VALID_TASKS_FILTERS",
    "_VALID_TASKS_SORT_MODES",
    "MeUpdateRequest",
    "delete_background",
    "get_background",
    "get_today",
    "me",
    "update_me",
    "upload_background",
    # admin_users
    "_ADMIN_USER_FIELDS",
    "_all_module_ids",
    "_VALID_POOLS",
    "CreateUserRequest",
    "DeletionDecision",
    "DeletionExecuteRequest",
    "ModuleAccessRequest",
    "PoolEditRequest",
    "RoleUpdateRequest",
    "UpdateRoleRequest",
    "UserUpdateRequest",
    "WorkspaceModulesRequest",
    "WorkspacesRequest",
    "admin_create_user",
    "admin_delete_user",
    "admin_list_users",
    "admin_update_user_role",
    "admin_user_deletion_execute",
    "admin_user_deletion_preview",
    "list_users_legacy",
    "update_user_by_admin",
    "update_user_modules",
    "update_user_pool_edit",
    "update_user_role_legacy",
    "update_user_workspaces",
    "update_workspace_modules",
    # admin_settings
    "_automation_token_limit",
    "_HOSTING_SETTINGS_PATH",
    "AdminSettingsRequest",
    "HostingSettingsRequest",
    "SearchSettingsRequest",
    "ai_settings_path",
    "apply_hosting_settings",
    "get_admin_settings",
    "get_automation_token",
    "get_hosting_settings",
    "get_search_settings",
    "rotate_automation_token",
    "update_admin_settings",
    "update_search_settings",
]
