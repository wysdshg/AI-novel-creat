// 写作 SKILL API 封装（全局共享） —— 后端 /api/v1/global-skills
// 注意：本文件与资料库的 skillApi（/projects/{id}/skills）独立，互不影响。
import http from './http'

function buildSearch(params = {}) {
  const out = {}
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') out[k] = v
  }
  return out
}

export const customSkillApi = {
  list: (params = {}) => http.get('/global-skills', { params: buildSearch(params) }),
  get: (id) => http.get(`/global-skills/${id}`),
  create: (data) => http.post('/global-skills', data),
  update: (id, data) => http.put(`/global-skills/${id}`, data),
  remove: (id) => http.delete(`/global-skills/${id}`),
}
