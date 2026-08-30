// Journal's API client — built on the shared request/get/put/del helpers
// exported from the core lib/api.js (session handling, error normalization),
// not a reimplementation of fetch/credentials/header logic per module.
import { get, put, del } from '../../../lib/api'

export const journal = {
  list:   ()                => get('/journal'),
  get:    (date)            => get(`/journal/${date}`),
  upsert: (date, content)   => put(`/journal/${date}`, { content }),
  setTags: (date, tags)     => put(`/journal/${date}/tags`, { tags }),
  remove: (date)            => del(`/journal/${date}`),
}
