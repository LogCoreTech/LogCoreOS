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
// Goals (/goals) is deliberately NOT declared here — it was never a real
// backend-gated module (no require_module("goals") exists; App.jsx has
// always gated /goals on moduleId="tasks", the same permission as /tasks
// itself) and stays exactly the hand-maintained CORE_MODULES nav entry it
// already was. Only the FILE moved into this package's frontend/ folder;
// its own content/help.json section and its lib/constants.js nav entry
// both stay untouched. See docs/MEMORY.md's 2026-08-25 entry for the full
// reasoning against generalizing the manifest schema to support multiple
// pages per module — Goals sharing Tasks' permission gate never actually
// required that.
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
      type: 'goals_progress',
      loadComponent: () => import('./frontend/GoalsProgressBlock.jsx'),
      icon: '🏆',
      label: 'Goals Progress',
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
