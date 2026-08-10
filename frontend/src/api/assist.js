import http from './http'

// AI 辅助能力：去AI味检测 / SKILL 调度查询 / 全局配置 / 记忆 / 实体确认
export const assistApi = {
  // 去 AI 味：纯正则扫描，不调模型
  scanText: (text, scene = 'novel') => http.post('/humanize/scan', { text, scene }),
  scanChapter: (projectId, chapterId) =>
    http.post(`/projects/${projectId}/chapters/${chapterId}/scan`),
  humanizePrompt: (scene = 'novel', level = 'normal') =>
    http.get('/humanize/prompt', { params: { scene, level } }),

  // SKILL 调度：哪些生效、哪些被同类高优先级挤掉
  dispatch: (trigger = 'chapter') => http.get('/skills/dispatch', { params: { trigger } }),
  seedSkills: (overwrite = false) => http.post('/skills/seed', null, { params: { overwrite } }),

  // 全局配置（KV）
  getConfig: () => http.get('/config'),
  updateConfig: (payload) => http.put('/config', payload),

  // 参考资料推荐（从全局池挑值得导入本作品的）
  recommendReferences: (projectId, topK = 8) =>
    http.get(`/projects/${projectId}/references/recommend`, { params: { top_k: topK } }),
}

export const memoryApi = {
  ingest: (projectId, chapterId) => http.post(`/projects/${projectId}/memory/ingest/${chapterId}`),
  listChapters: (projectId, articleId) =>
    http.get(`/projects/${projectId}/memory/chapters`, { params: { article_id: articleId } }),
  get: (projectId, chapterId) => http.get(`/projects/${projectId}/memory/chapters/${chapterId}`),
  summary: (projectId) => http.get(`/projects/${projectId}/memory/summary`),
  stages: (projectId) => http.get(`/projects/${projectId}/memory/stages`),
  events: (projectId) => http.get(`/projects/${projectId}/memory/events`),
  pendingEntities: (projectId) => http.get(`/projects/${projectId}/memory/pending-entities`),
  confirmEntities: (projectId, chapterId, items) =>
    http.post(`/projects/${projectId}/memory/confirm-entities`, { chapter_id: chapterId, items }),
  compress: (projectId, fromNo, toNo) =>
    http.post(`/projects/${projectId}/memory/compress`, null, {
      params: { from_no: fromNo, to_no: toNo },
    }),
}
