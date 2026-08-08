// 模块3：剧情商讨（需求 6）。
import http from './http'

// 流式对话（SSE，使用 fetch 直接读流）
export async function discussionChatStream(projectId, body, onEvent) {
  const resp = await fetch(`/api/v1/projects/${projectId}/discussion/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    throw new Error(`商讨接口返回 ${resp.status}`)
  }
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

// 读取「当前商讨缓存」（已持久化）
export function discussionLoad(projectId) {
  return http.get(`/projects/${projectId}/discussion`)
}

// 手动追加一条消息（闲聊、不调模型）
export function discussionAppend(projectId, payload) {
  return http.post(`/projects/${projectId}/discussion/messages`, payload)
}

// 清空当前商讨缓存
export function discussionClear(projectId) {
  return http.delete(`/projects/${projectId}/discussion`)
}

// 将当前草稿归档为指定章节备注
export function discussionArchive(projectId, chapterId) {
  return http.post(`/projects/${projectId}/discussion/archive?chapter_id=${encodeURIComponent(chapterId)}`)
}
