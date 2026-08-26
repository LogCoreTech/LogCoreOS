// Team's API client — built on the shared request/get/post/patch/del
// helpers exported from the core lib/api.js, not a reimplementation of
// fetch/credentials/header logic per module.
import { get, post, patch, del } from '../../../lib/api'

export const team = {
  list:  ()           => get('/team/tasks'),
  add:   (task)        => post('/team/tasks', task),
  update: (id, upd)    => patch(`/team/tasks/${id}`, upd),
  remove: (id)          => del(`/team/tasks/${id}`),
  members: ()           => get('/team/members'),
  sharedEvents: ()       => get('/team/events'),
  addSharedEvent: (body) => post('/team/events', body),
  updateSharedEvent: (id, body) => patch(`/team/events/${id}`, body),
  removeSharedEvent: (id) => del(`/team/events/${id}`),
}
