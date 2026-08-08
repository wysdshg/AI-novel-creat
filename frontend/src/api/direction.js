import http from './http'

// 模块7：剧情走向推荐（需求 5）
export const directionApi = {
  recommend: (projectId, chapterId) =>
    http.post(`/projects/${projectId}/chapters/${chapterId}/directions`),
  list: (projectId, chapterId) =>
    http.get(`/projects/${projectId}/chapters/${chapterId}/directions`),
  select: (projectId, directionId) =>
    http.post(`/projects/${projectId}/directions/${directionId}/select`),
}
