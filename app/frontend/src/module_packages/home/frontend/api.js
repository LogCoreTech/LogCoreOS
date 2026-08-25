// Home's API client — built on the shared request/get/post/put helpers
// exported from the core lib/api.js (session handling, error normalization),
// not a reimplementation of fetch/credentials/header logic per module.
// Also imported by pages/settings/admin/Household.jsx (a different,
// not-yet-converted module's page) for status()/saveConfig() — see
// docs/MEMORY.md's 2026-08-24 Home-conversion entry for why the HA config
// form lives there rather than in a dedicated Home admin page.
import { get, post, put } from '../../../lib/api'

export const home = {
  status:            ()                => get('/home/status'),
  saveConfig:        (cfg)             => post('/home/config', cfg),
  entities:          (domain)          => get(`/home/entities${domain ? `?domain=${domain}` : ''}`),
  entity:            (entity_id)       => get(`/home/entities/${entity_id}`),
  callService:       (entity_id, body) => post(`/home/entities/${entity_id}/call`, body),
  areas:             ()                => get('/home/areas'),
  scenes:            ()                => get('/home/scenes'),
  activateScene:     (entity_id)       => post(`/home/scenes/${entity_id}/activate`, {}),
  automations:       ()                => get('/home/automations'),
  triggerAutomation: (entity_id)       => post(`/home/automations/${entity_id}/trigger`, {}),
  getFavourites:     ()                => get('/home/favourites'),
  saveFavourites:    (entity_ids)      => put('/home/favourites', { entity_ids }),
}
