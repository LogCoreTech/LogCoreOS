// Tasks' frontend manifest — discovered by src/lib/moduleRegistry.js's
// import.meta.glob. Mirrors the backend manifest's shape (same id, same
// icon-for-nav) but only carries what the frontend actually needs.
//
// Tasks is the first LOCKED module conversion — its backend manifest sets
// uninstallable=True, so ModStore.jsx always shows it "Always active," no
// uninstall button. Nothing about the FRONTEND manifest shape changes for a
// locked module though: `to`/`recordParam` still merge into MODULE_ROUTES/
// RECORD_PARAM the same way every optional module's already do, and
// ModuleRoute's installed+active check still applies identically — a locked
// module just always resolves both true, by construction (its own upgrade
// migration marks it installed unconditionally, no existence guard).
//
// Goals (/goals) rode this module's own permission gate from 2026-08-25
// until 2026-08-28, when it converted into its own real module,
// module_packages/goals/ — own manifest, own require_module("goals") gate,
// own route. Goals.jsx and GoalsProgressBlock.jsx both moved out of this
// package's frontend/ folder to goals/'s own.
export default {
  id: 'tasks',
  to: '/tasks',
  icon: '✓',
  label: 'Tasks',
  recordParam: 'task',
  loadPage: () => import('./frontend/Tasks.jsx'),
  blocks: [
    {
      type: 'top3_tasks',
      loadComponent: () => import('./frontend/Top3TasksBlock.jsx'),
      icon: '🎯',
      label: 'Top 3 Tasks',
      defaultLayout: { w: 12, h: 9 },
      shape: 'list',
      recordKind: 'task',
      configSchema: [
        {
          key: 'sort_mode',
          label: 'Sort by',
          kind: 'select',
          optional: true,
          options: [
            { value: 'priority', label: 'Priority' },
            { value: 'date', label: 'Date/Time' },
            { value: 'alpha', label: 'A–Z' },
          ],
        },
      ],
    },
    {
      type: 'due_today',
      loadComponent: () => import('./frontend/DueTodayBlock.jsx'),
      icon: '📅',
      label: 'Due Today',
      defaultLayout: { w: 12, h: 9 },
      shape: 'list',
      recordKind: 'task',
      configSchema: [
        {
          key: 'sort_mode',
          label: 'Sort by',
          kind: 'select',
          optional: true,
          options: [
            { value: 'priority', label: 'Priority' },
            { value: 'date', label: 'Date/Time' },
            { value: 'alpha', label: 'A–Z' },
          ],
        },
      ],
    },
    {
      type: 'streaks',
      loadComponent: () => import('./frontend/StreaksBlock.jsx'),
      icon: '🔥',
      label: 'Active Streaks',
      defaultLayout: { w: 12, h: 9 },
      shape: 'list',
      recordKind: 'task',
    },
    {
      type: 'single_task',
      loadComponent: () => import('./frontend/SingleTaskBlock.jsx'),
      icon: '✅',
      label: 'Single Task',
      defaultLayout: { w: 9, h: 6 },
      recordKind: 'task',
      configSchema: [{ key: 'task_id', label: 'Task', kind: 'task' }],
    },
  ],
}
