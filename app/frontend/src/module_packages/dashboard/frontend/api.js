import { get, post, patch, put, del } from '../../../lib/api'

export const dashboards = {
  list:          ()                       => get('/dashboards'),
  get:           (id)                     => get(`/dashboards/${id}`),
  render:        (id)                     => get(`/dashboards/${id}/render`),
  create:        (name, icon, pool = false, templateId = null, subjectId = null) =>
    post('/dashboards', { name, icon, pool, template_id: templateId, subject_id: subjectId }),
  update:        (id, data)               => patch(`/dashboards/${id}`, data),
  remove:        (id)                     => del(`/dashboards/${id}`),
  catalog:       ()                       => get('/dashboards/catalog'),
  members:       ()                       => get('/dashboards/members'),
  roles:         ()                       => get('/dashboards/roles'),
  updateAccess:  (id, data)               => put(`/dashboards/${id}/access`, data),
  setShareUnderlyingData: (id, value)     => put(`/dashboards/${id}/share-underlying-data`, { value }),
  setSubject:    (id, subjectId)          => put(`/dashboards/${id}/subject`, { subject_id: subjectId }),
  detachTemplate: (id)                    => post(`/dashboards/${id}/detach-template`, {}),
  leave:         (id)                     => post(`/dashboards/${id}/leave`, {}),
  respondShare:  (owner, dashboardId, accept) => post('/dashboards/shares/respond', { owner, dashboard_id: dashboardId, accept }),
  references:    (module, recordId)       => get(`/dashboards/references/${module}/${recordId}`),
}

export const dashboardTemplates = {
  list:           ()               => get('/dashboards/templates'),
  create:         (data)           => post('/dashboards/templates', data),
  update:         (id, data)       => patch(`/dashboards/templates/${id}`, data),
  remove:         (id)             => del(`/dashboards/templates/${id}`),
  access:         (id, data)       => put(`/dashboards/templates/${id}/access`, data),
  leave:          (id)             => post(`/dashboards/templates/${id}/leave`, {}),
  respondShare:   (owner, templateId, accept) =>
    post('/dashboards/templates/shares/respond', { owner, template_id: templateId, accept }),
}
