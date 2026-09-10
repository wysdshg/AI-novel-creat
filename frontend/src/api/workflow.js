// 工作流 API 封装（全局共享） —— 后端 /api/v1/workflows
import http from './http'

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
  if (!resp.ok) {
    // 后端把配置错误（单 start/end、环等）作为 400 提前暴露
    let msg = `运行接口返回 ${resp.status}`
    try {
      const body = await resp.json()
      if (body?.message) msg = body.message
    } catch { /* 非 JSON 错误体，保留默认提示 */ }
    throw new Error(msg)
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() || ''
    for (const block of blocks) {
      const ev = /event: (.+)/.exec(block)
      const data = /data: (.+)/.exec(block)
      if (ev && data) {
        try {
          onEvent?.(ev[1], JSON.parse(data[1]))
        } catch { /* 忽略单条畸形 SSE */ }
      }
    }
  }
}
