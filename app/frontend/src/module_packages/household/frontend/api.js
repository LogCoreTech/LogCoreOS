// Household's API client — built on the shared request/get/post/patch/del
// helpers exported from the core lib/api.js, not a reimplementation of
// fetch/credentials/header logic per module. Endpoints stay mounted at
// /shared (not /household) — the historical prefix, unrelated to the
// module id, unchanged by this conversion.
import { get, post, patch, del } from '../../../lib/api'

export const shared = {
  list:  ()           => get('/shared/tasks'),
  add:   (task)        => post('/shared/tasks', task),
  update: (id, upd)    => patch(`/shared/tasks/${id}`, upd),
  remove: (id)          => del(`/shared/tasks/${id}`),
  members: ()           => get('/shared/members'),
  sharedEvents: ()       => get('/shared/events'),
  addSharedEvent: (body) => post('/shared/events', body),
  updateSharedEvent: (id, body) => patch(`/shared/events/${id}`, body),
  removeSharedEvent: (id) => del(`/shared/events/${id}`),
}
