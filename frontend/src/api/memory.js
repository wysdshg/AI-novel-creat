import http from './http'

// 模块5：篇章记忆压缩（需求 8）
export const memoryApi = {
  compress: (projectId, chapterId) =>
    http.post(`/projects/${projectId}/memory/compress`, { chapterId }),
  summary: (projectId) => http.get(`/projects/${projectId}/memory/summary`),
  events: (projectId) => http.get(`/projects/${projectId}/memory/events`),
}
