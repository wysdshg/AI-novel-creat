import http from './http'

// 4 级结构（小说→卷→篇→章）——「卷」层
export const volumeApi = {
  list: (projectId) => http.get(`/projects/${projectId}/volumes`),
  get: (projectId, id) => http.get(`/projects/${projectId}/volumes/${id}`),
  create: (projectId, data) => http.post(`/projects/${projectId}/volumes`, data),
  update: (projectId, id, data) => http.put(`/projects/${projectId}/volumes/${id}`, data),
  remove: (projectId, id) => http.delete(`/projects/${projectId}/volumes/${id}`),
}
