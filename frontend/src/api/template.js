import http from './http'

// 模块8：小说套路模板组件（需求 11）
export const templateApi = {
  list: () => http.get('/templates'),
  generateOutline: (projectId, templateId, data) =>
    http.post(`/projects/${projectId}/templates/${templateId}/outline`, data),
  listOutlines: (projectId) => http.get(`/projects/${projectId}/outlines`),
  createOutline: (projectId, data) => http.post(`/projects/${projectId}/outlines`, data),
  updateOutline: (projectId, id, data) => http.put(`/projects/${projectId}/outlines/${id}`, data),
  removeOutline: (projectId, id) => http.delete(`/projects/${projectId}/outlines/${id}`),
}
