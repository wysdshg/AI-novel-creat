// 工作流 API 封装（全局共享） —— 后端 /api/v1/workflows
import http from './http'
import { readSseStream } from '@/utils/sse'

function buildSearch(params = {}) {
  const out = {}
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') out[k] = v
  }
  return out
}

export const workflowApi = {
  list: (params = {}) => http.get('/workflows', { params: buildSearch(params) }),
  get: (id) => http.get(`/workflows/${id}`),
  create: (data) => http.post('/workflows', data),
  update: (id, data) => http.put(`/workflows/${id}`, data),
  remove: (id) => http.delete(`/workflows/${id}`),
  duplicate: (id) => http.post(`/workflows/${id}/duplicate`),
  // —— 运行 ——
  nodeTypes: () => http.get('/workflows/meta/node-types'),
  runs: (wfId) => http.get(`/workflows/${wfId}/runs`),
  runDetail: (runId) => http.get(`/workflows/runs/${runId}`),
}

// SSE 流式运行工作流（fetch 直读流；onEvent(event, data)）
export async function workflowRunStream(wfId, inputs, onEvent) {
  const resp = await fetch(`/api/v1/workflows/${wfId}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ inputs }),
  })
  // 状态校验 / 读流统一在 readSseStream（Phase 3.3）。
  // 后端把配置错误（单 start/end、环等）作为 400 提前暴露，错误体 message 优于状态码 → errorPrefix 会被 detail 覆盖。
  // 本地工作流不容忍畸形帧（错误应尽早暴露）→ tolerant: false。
  await readSseStream(resp, onEvent, {
    errorPrefix: '运行接口',
    tolerant: false,
  })
}

