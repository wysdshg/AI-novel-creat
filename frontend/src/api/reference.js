import http from './http'

// 每本小说的参考文档（用户手动上传，供 AI 生成时参考读取）
export const referenceApi = {
  list: (projectId) => http.get(`/projects/${projectId}/references`),
  get: (projectId, docId) => http.get(`/projects/${projectId}/references/${docId}`),
  // body: { filename, content_type, size, content_text }
  upload: (projectId, body) => http.post(`/projects/${projectId}/references`, body),
  remove: (projectId, docId) => http.delete(`/projects/${projectId}/references/${docId}`),
  rename: (projectId, docId, filename) => http.put(`/projects/${projectId}/references/${docId}`, { filename }),
}

// 全局共享参考资料池（「参考资料」）——与小说维度共用后端但 project_id 隔离
export const globalReferenceApi = {
  list: () => http.get('/references/global'),
  get: (docId) => http.get(`/references/global/${docId}`),
  // body: { filename, content_type, size, content_text }
  upload: (body) => http.post('/references/global', body),
  remove: (docId) => http.delete(`/references/global/${docId}`),
  rename: (docId, filename) => http.put(`/references/global/${docId}`, { filename }),
  // 新建小说时，将选中的全局参考资料复制进该小说
  importToProject: (projectId, docIds) => http.post(`/projects/${projectId}/references/import-global`, { doc_ids: docIds }),
}
