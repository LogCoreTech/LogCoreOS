// Household's frontend manifest — discovered by src/lib/moduleRegistry.js's
// import.meta.glob. Mirrors the backend manifest's shape (same id, same
// icon-for-nav) but only carries what the frontend actually needs.
// `workspace: 'personal'` matches constants.js's own CORE_MODULES entry
// this replaces. `household_tasks` is the personal-workspace half of the
// old shared `pool_tasks` block, split apart when household/team converted
// (2026-08-25) — see team/manifest.js for the business-workspace half and
// the backend manifest's m023 migration for why a single block type
// couldn't stay shared once both pools became real, gated modules. No
// recordKind (never had per-row actions before either) — rows route
// through this module's own `shared` API client, never `tasksApi`.
export default {
  id: 'household',
  to: '/household',
  icon: '🏠',
  label: 'Household',
  workspace: 'personal',
  loadPage: () => import('./frontend/Household.jsx'),
  blocks: [
    {
      type: 'household_tasks',
      loadComponent: () => import('./frontend/HouseholdTasksBlock.jsx'),
      icon: '🏠',
      label: 'Household Pool Tasks',
      defaultLayout: { w: 12, h: 9 },
      shape: 'list',
    },
    {
      type: 'household_goals',
      loadComponent: () => import('./frontend/HouseholdGoalsBlock.jsx'),
      icon: '🎯',
      label: 'Household Pool Goals',
      defaultLayout: { w: 12, h: 9 },
      shape: 'list',
    },
  ],
}
