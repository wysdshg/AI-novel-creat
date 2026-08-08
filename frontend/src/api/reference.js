import http from './http'

// 每本小说的参考文档（用户手动上传，供 AI 生成时参考读取）
export const referenceApi = {
  list: (projectId) => http.get(`/projects/${projectId}/references`),
  get: (projectId, docId) => http.get(`/projects/${projectId}/references/${docId}`),
  // body: { filename, content_type, size, content_text }
  upload: (projectId, body) => http.post(`/projects/${projectId}/references`, body),
  remove: (projectId, docId) => http.delete(`/projects/${projectId}/references/${docId}`),
}
