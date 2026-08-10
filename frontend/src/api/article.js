import http from './http'

// 4 级结构 小说→卷→篇→章 ——「篇」层
export const articleApi = {
  list: (projectId, params) => http.get(`/projects/${projectId}/articles`, { params }),
  get: (projectId, id) => http.get(`/projects/${projectId}/articles/${id}`),
  create: (projectId, volumeId, data) =>
    http.post(`/projects/${projectId}/volumes/${volumeId}/articles`, { ...data, volume_id: volumeId }),
  update: (projectId, id, data) => http.put(`/projects/${projectId}/articles/${id}`, data),
  remove: (projectId, id) => http.delete(`/projects/${projectId}/articles/${id}`),
  // 篇下挂章
  listChapters: (articleId) => http.get(`/articles/${articleId}/chapters`),
  createChapter: (articleId, data) =>
    http.post(`/articles/${articleId}/chapters`, { ...data, article_id: articleId }),
}
