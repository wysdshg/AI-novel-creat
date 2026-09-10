// 生成评估 API 封装（Phase 4.1 最小 eval） —— 后端 /api/v1
// 版本由生成链路自动留档，本模块只做「查询 / 打分 / 删除」。
import http from './http'

export const evalApi = {
  // 列出某章的全部生成版本（含最新评分，按时间倒序）
  listVariants: (projectId, chapterId) =>
    http.get(`/projects/${projectId}/chapters/${chapterId}/variants`),

  // 对比视图：总数 / 已评数 / 均分 / 最高分及其配置
  compare: (projectId, chapterId) =>
    http.get(`/projects/${projectId}/chapters/${chapterId}/variants/compare`),

  // 版本详情（含正文全文）
  getVariant: (variantId) => http.get(`/variants/${variantId}`),

  // 打分：{ score: 1~5, comment?: string }
  score: (variantId, data) => http.post(`/variants/${variantId}/eval`, data),

  remove: (variantId) => http.delete(`/variants/${variantId}`),
}
