// Home Assistant's API client — built on the shared request/get/post/put
// helpers exported from the core lib/api.js (session handling, error
// normalization), not a reimplementation of fetch/credentials/header logic
// per module. Also imported by pages/settings/admin/Hosting.jsx (a
// different, not-yet-converted module's page) for status()/saveConfig() —
// see docs/MEMORY.md's 2026-08-24 entries for why the HA config form lives
// there rather than in a dedicated Home Assistant admin page. Paths use
// /home_assistant/... (backend router_prefix, renamed from /home/...
// alongside the module id, 2026-08-24).
import { get, post, put } from '../../../lib/api'

export const home = {
  status:            ()                => get('/home_assistant/status'),
  saveConfig:        (cfg)             => post('/home_assistant/config', cfg),
  entities:          (domain)          => get(`/home_assistant/entities${domain ? `?domain=${domain}` : ''}`),
  entity:            (entity_id)       => get(`/home_assistant/entities/${entity_id}`),
  callService:       (entity_id, body) => post(`/home_assistant/entities/${entity_id}/call`, body),
  areas:             ()                => get('/home_assistant/areas'),
  scenes:            ()                => get('/home_assistant/scenes'),
  activateScene:     (entity_id)       => post(`/home_assistant/scenes/${entity_id}/activate`, {}),
  automations:       ()                => get('/home_assistant/automations'),
  triggerAutomation: (entity_id)       => post(`/home_assistant/automations/${entity_id}/trigger`, {}),
  getFavourites:     ()                => get('/home_assistant/favourites'),
  saveFavourites:    (entity_ids)      => put('/home_assistant/favourites', { entity_ids }),
}
