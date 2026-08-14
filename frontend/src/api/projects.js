import http from './http'

// 作品（项目）隔离管理（§1）
export const projectApi = {
  list: (params) => http.get('/projects', { params }),
  create: (data) => http.post('/projects', data),
  get: (id) => http.get(`/projects/${id}`),
  update: (id, data) => http.put(`/projects/${id}`, data),
  remove: (id) => http.delete(`/projects/${id}`),
  // 小说设定库管理
  getSettings: (id) => http.get(`/projects/${id}/settings`),
  updateSettings: (id, settingIds) => http.put(`/projects/${id}/settings`, { setting_ids: settingIds }),
  // 手动刷新整本概览（篇/卷/小说三级 LLM 压缩）
  aggregateOverview: (id, data) => http.post(`/projects/${id}/aggregate-overview`, data || {}),
}
