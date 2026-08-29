// Goals' frontend manifest — discovered by src/lib/moduleRegistry.js's
// import.meta.glob. Mirrors the backend manifest's shape (same id, same
// icon-for-nav) but only carries what the frontend actually needs.
//
// Not a mechanical conversion like the 13-module rollout — this is a
// genuinely new module. goals_progress replaces the old block that lived
// under tasks/ (rebuilt to show real computed progress instead of a bare
// task list). Pool variants (household_goals/team_goals) live in
// household's/team's own manifest.js, not here — same split
// household_tasks/team_tasks already established.
export default {
  id: 'goals',
  to: '/goals',
  icon: '🎯',
  label: 'Goals',
  recordParam: 'goal',
  loadPage: () => import('./frontend/Goals.jsx'),
  blocks: [
    {
      type: 'goals_progress',
      loadComponent: () => import('./frontend/GoalsProgressBlock.jsx'),
      icon: '🎯',
      label: 'Goals Progress',
      defaultLayout: { w: 12, h: 9 },
      shape: 'list',
    },
  ],
}
