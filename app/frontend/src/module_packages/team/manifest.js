// Team's frontend manifest — discovered by src/lib/moduleRegistry.js's
// import.meta.glob. Mirrors the backend manifest's shape (same id, same
// icon-for-nav) but only carries what the frontend actually needs.
// `workspace: 'business'` matches constants.js's own CORE_MODULES entry
// this replaces. `team_tasks` is the business-workspace half of the old
// shared `pool_tasks` block — see household/manifest.js for the fuller
// reasoning this mirrors.
export default {
  id: 'team',
  to: '/team',
  icon: '🧑‍🤝‍🧑',
  label: 'Team',
  workspace: 'business',
  loadPage: () => import('./frontend/Team.jsx'),
  blocks: [
    {
      type: 'team_tasks',
      loadComponent: () => import('./frontend/TeamTasksBlock.jsx'),
      icon: '🧑‍🤝‍🧑',
      label: 'Team Pool Tasks',
      defaultLayout: { w: 12, h: 9 },
      shape: 'list',
    },
    {
      type: 'team_goals',
      loadComponent: () => import('./frontend/TeamGoalsBlock.jsx'),
      icon: '🎯',
      label: 'Team Pool Goals',
      defaultLayout: { w: 12, h: 9 },
      shape: 'list',
    },
  ],
}
