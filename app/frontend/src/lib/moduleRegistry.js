// Auto-discovers every converted module's frontend manifest at BUILD time —
// no per-module edit to App.jsx/constants.js/deepLinks.js ever again once a
// module lives under module_packages/. `eager: true` on the manifests
// themselves is fine (they're tiny, no heavy component code); each
// manifest's own `loadPage`/`block.loadComponent` is a real dynamic
// import() that Vite code-splits into its own chunk, downloaded only when
// actually routed to or rendered.
//
// A module's presence here means "shipped in this build" (the backend
// equivalent: discover_manifests()) — NOT "installed" or "active". Nav/
// routing gate on the separate activeModuleIds from AuthProvider
// (GET /mod-store/active); admin-configuration surfaces (role editor,
// shortcuts picker) intentionally show every discovered module regardless
// of state, matching how the backend's role validation already accepts any
// discovered module id.

const manifestModules = import.meta.glob('/src/module_packages/*/manifest.js', { eager: true })

export const MODULE_PACKAGES = Object.values(manifestModules)
  .map(m => m.default)
  .filter(Boolean)

export const MODULE_PACKAGE_IDS = new Set(MODULE_PACKAGES.map(m => m.id))

export function isPackageModule(moduleId) {
  return MODULE_PACKAGE_IDS.has(moduleId)
}
