import http from './http'

// 模块6：伏笔线索自动化管理（需求 9）
export const foreshadowApi = {
  list: (projectId, params) => http.get(`/projects/${projectId}/foreshadows`, { params }),
  get: (projectId, id) => http.get(`/projects/${projectId}/foreshadows/${id}`),
  create: (projectId, data) => http.post(`/projects/${projectId}/foreshadows`, data),
  update: (projectId, id, data) => http.put(`/projects/${projectId}/foreshadows/${id}`, data),
  remove: (projectId, id) => http.delete(`/projects/${projectId}/foreshadows/${id}`),
  detect: (projectId, chapterId) =>
    http.post(`/projects/${projectId}/foreshadows/detect`, { chapterId }),
  active: (projectId) => http.get(`/projects/${projectId}/foreshadows/active`),
  activate: (projectId, id, activatedChapter) =>
    http.post(`/projects/${projectId}/foreshadows/${id}/activate`, { activatedChapter }),
}
