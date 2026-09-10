// 观测消费端 API（Phase 4.2 用量计量 + 4.3 反馈回流） —— 后端 /api/v1
import http from './http'

export const usageApi = {
  // 用量聚合统计：{ overall, by_model, by_scene, trend, recent }
  summary: (params = {}) => http.get('/usage/summary', { params }),
  clear: (params = {}) => http.delete('/usage', { params }),
}

export const feedbackApi = {
  // 反馈记录列表（kind=chapter_edit 等）
  list: (params = {}) => http.get('/feedback', { params }),
  // 聚合：{ total, avg_similarity, avg_change_ratio, by_kind }
  stats: (params = {}) => http.get('/feedback/stats', { params }),
  clear: (params = {}) => http.delete('/feedback', { params }),
}
