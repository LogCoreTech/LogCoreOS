// Calendar's API client — built on the shared request/get/post/patch/del
// helpers exported from the core lib/api.js, not a reimplementation of
// fetch/credentials/header logic per module.
import { get, post, patch, del } from '../../../lib/api'

export const calendar = {
  tasks:       ()           => get('/calendar/tasks'),
  events:      ()           => get('/calendar/events'),
  addEvent:    (body)       => post('/calendar/events', body),
  getEvent:    (id)         => get(`/calendar/events/${id}`),
  updateEvent: (id, body)   => patch(`/calendar/events/${id}`, body),
  removeEvent: (id)         => del(`/calendar/events/${id}`),
}
