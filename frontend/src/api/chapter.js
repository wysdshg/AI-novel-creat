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
export async function generateChapterStream(projectId, body, onEvent) {
  const resp = await fetch(`/api/v1/projects/${projectId}/chapters/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
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
}
