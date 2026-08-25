// Tasks' API client — built on the shared request/get/post/patch/del
// helpers exported from the core lib/api.js, not a reimplementation of
// fetch/credentials/header logic per module.
import { get, post, patch, del } from '../../../lib/api'

export const tasks = {
  list:     ()                             => get('/tasks'),
  top3:     ()                             => get('/tasks/top3'),
  scored:   ()                             => get('/tasks/scored'),
  assigned: ()                             => get('/tasks/assigned'),
  history:  (limit = 50, offset = 0)       => get(`/tasks/history?limit=${limit}&offset=${offset}`),
  add:      (task)                         => post('/tasks', task),
  update:   (id, updates)                  => patch(`/tasks/${id}`, updates),
  remove:   (id)                           => del(`/tasks/${id}`),
  cleanupGoals: ()                         => post('/tasks/goals/cleanup', {}),
}
