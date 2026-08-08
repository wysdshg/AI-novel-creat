import http from './http'

// 模块4：多厂商统一 API 网关（需求 7）。全局配置，不含 projectId。
export const modelApi = {
  list: () => http.get('/models'),
  get: (id) => http.get(`/models/${id}`),
  create: (data) => http.post('/models', data),
  update: (id, data) => http.put(`/models/${id}`, data),
  remove: (id) => http.delete(`/models/${id}`),
  setDefault: (id) => http.post(`/models/${id}/set-default`),
  test: (data) => http.post('/models/test', data),
}
