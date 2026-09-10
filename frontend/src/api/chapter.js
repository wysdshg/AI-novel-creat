import http from './http'

// 模块2/3：章节生成 + 剧情商讨（需求 2、3、6）
export const chapterApi = {
  list: (projectId, params) => http.get(`/projects/${projectId}/chapters`, { params }),
  get: (projectId, id) => http.get(`/projects/${projectId}/chapters/${id}`),
  create: (projectId, data) => http.post(`/projects/${projectId}/chapters`, data),
  update: (projectId, id, data) => http.put(`/projects/${projectId}/chapters/${id}`, data),
  remove: (projectId, id) => http.delete(`/projects/${projectId}/chapters/${id}`),
}

// 流式单章生成（SSE，§3.3）。脚手架：用 fetch 读取事件流，回调 onEvent。
// 真实接入后用后端 /projects/{projectId}/chapters/generate 的 SSE 事件。
// 支持传入 { signal: AbortSignal, modelId } 实现手动停止并指定模型；中止后抛 GenerationStopped 错误。
export async function generateChapterStream(projectId, body, onEvent, { signal, modelId } = {}) {
  if (modelId) body.model_id = modelId
  const resp = await fetch(`/api/v1/projects/${projectId}/chapters/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  // ⚠️ 必须显式校验 HTTP 状态：后端在 400/500 时返回的是 JSON 错误体（不是 SSE），
  // 不校验就会拿它当事件流解析 → 前端只看到"完全没有输出"，错误信息被吞掉（静默失败）。
  // 典型场景：漏传 article_id 后端返回 400「生成章节必须指定所属篇」。
  if (!resp.ok) {
    let detail = ''
    try {
      const j = await resp.json()
      detail = j?.detail || j?.message || ''
    } catch {
      /* 错误体不是 JSON 就忽略，用状态码兜底 */
    }
    throw new Error(detail || `章节生成接口返回 ${resp.status}`)
  }
  if (!resp.body) {
    throw new Error('章节生成接口未返回数据流')
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop() || ''
      for (const block of events) {
        const ev = /event: (.+)/.exec(block)
        const data = /data: (.+)/.exec(block)
        if (ev && data) onEvent?.(ev[1], JSON.parse(data[1]))
      }
    }
  } catch (e) {
    if (e?.name === 'AbortError') {
      const err = new Error('生成已停止')
      err.name = 'GenerationStopped'
      throw err
    }
    throw e
  }
}
