// Homes' API client — built on the shared request/get/post/patch/del
// helpers exported from the core lib/api.js, not a reimplementation of
// fetch/credentials/header logic per module.
import { get, post, patch, del } from '../../../lib/api'

export const homes = {
  list:    ()                    => get('/homes'),
  get:     (id, pool = false)    => get(`/homes/${id}?pool=${pool}`),
  items:   (id, pool = false)    => get(`/homes/${id}/items?pool=${pool}`),
  create:  (data)                => post('/homes', data),
  update:  (id, updates)         => patch(`/homes/${id}`, updates),
  remove:  (id, pool = false)    => del(`/homes/${id}?pool=${pool}`),
  bulkDelete: (ids, pool = false) => post('/homes/bulk-delete', { ids, pool }),
  convertToPool: (id)             => post(`/homes/${id}/convert-to-pool`, {}),
}
