// 工作流 API 封装（全局共享） —— 后端 /api/v1/workflows
import http from './http'

function buildSearch(params = {}) {
  const out = {}
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') out[k] = v
  }
  return out
}

export const workflowApi = {
  list: (params = {}) => http.get('/workflows', { params: buildSearch(params) }),
  get: (id) => http.get(`/workflows/${id}`),
  create: (data) => http.post('/workflows', data),
  update: (id, data) => http.put(`/workflows/${id}`, data),
  remove: (id) => http.delete(`/workflows/${id}`),
  duplicate: (id) => http.post(`/workflows/${id}/duplicate`),
}
