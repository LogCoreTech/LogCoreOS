// Goals' API client — built on the shared request/get/post/patch/del
// helpers exported from the core lib/api.js, not a reimplementation of
// fetch/credentials/header logic per module.
import { get, post, patch, del } from '../../../lib/api'

export const goals = {
  list:            ()                              => get('/goals'),
  get:              (id, pool = false)              => get(`/goals/${id}?pool=${pool}`),
  create:           (data)                          => post('/goals', data),
  update:           (id, updates)                   => patch(`/goals/${id}`, updates),
  remove:           (id, { pool = false, cascade = false, deleteLinkedTasks = false } = {}) =>
    del(`/goals/${id}?pool=${pool}&cascade=${cascade}&delete_linked_tasks=${deleteLinkedTasks}`),
  logMetric:        (id, value, date, pool = false)  => post(`/goals/${id}/metric/log`, { value, date, pool }),
  metricProviders:  ()                              => get('/goals/metric-providers'),
}
