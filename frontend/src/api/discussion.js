// 模块3：剧情商讨（需求 6）。
import http from './http'

const SSE_TIMEOUT_MS = 180000 // 与 axios timeout 一致，云端 LLM 常需 30~90s

/** 创建带超时的 AbortController，超时自动 abort 并抛出明确错误 */
function createTimeoutController(ms = SSE_TIMEOUT_MS) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), ms)
  return { controller, cleanup: () => clearTimeout(timer) }
}

// 流式对话（SSE，使用 fetch 直接读流）
// 支持外部传入 { signal } 实现手动停止；中止后抛 name='GenerationStopped' 的错误，
// 便于调用方与「网络/超时」错误区分开（否则中止会被当成失败弹红字）。
export async function discussionChatStream(projectId, body, onEvent, chapterId, { signal } = {}) {
  const q = chapterId ? `?chapter_id=${encodeURIComponent(chapterId)}` : ''
  // 注意：此处曾有 console.group 打印完整 Body / 最后一条用户消息正文 / system prompt。
  // 属隐私泄漏（用户输入全文进控制台），已移除（问题 1.1）。排查时只打无内容信息（条数/开关）。
  const { controller, cleanup } = createTimeoutController()
  // 外部 signal 与超时 controller 合并：任一触发即中止 fetch
  const onExternalAbort = () => controller.abort()
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', onExternalAbort, { once: true })
  }
  try {
    const resp = await fetch(`/api/v1/projects/${projectId}/discussion/chat${q}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
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
        if (ev && data) {
          try {
            onEvent?.(ev[1], JSON.parse(data[1]))
          } catch {
            /* 忽略单条畸形 SSE 数据，避免杀死整条流 */
          }
        }
      }
    }
  } catch (e) {
    if (e?.name === 'AbortError') {
      const err = new Error('已停止生成')
      err.name = 'GenerationStopped'
      throw err
    }
    throw e
  } finally {
    if (signal) signal.removeEventListener('abort', onExternalAbort)
    cleanup()
  }
}

// 全局对话（无需选择小说，类似豆包/ChatGPT 通用助手模式）
// 注入全局设定库 + 全局 SKILL，不含任何小说数据
export async function discussionGlobalChatStream(body, onEvent, { signal } = {}) {
  // 注意：此处曾有 console.group 打印完整 Body / 最后一条用户消息正文，属隐私泄漏，
  // 已移除（问题 1.1）。
  const { controller, cleanup } = createTimeoutController()
  const onExternalAbort = () => controller.abort()
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', onExternalAbort, { once: true })
  }
  try {
    const resp = await fetch('/api/v1/discussion/global-chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
    if (!resp.ok) {
      throw new Error(`全局对话接口返回 ${resp.status}`)
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
        if (ev && data) {
          try {
            onEvent?.(ev[1], JSON.parse(data[1]))
          } catch {
            /* 忽略单条畸形 SSE 数据，避免杀死整条流 */
          }
        }
      }
    }
  } catch (e) {
    if (e?.name === 'AbortError') {
      const err = new Error('已停止生成')
      err.name = 'GenerationStopped'
      throw err
    }
    throw e
  } finally {
    if (signal) signal.removeEventListener('abort', onExternalAbort)
    cleanup()
  }
}

// 读取「当前商讨缓存」（已持久化）；线程优先级：conversationId > chapter_id > 小说级默认线程
export function discussionLoad(projectId, chapterId, conversationId) {
  const q = []
  if (chapterId) q.push(`chapter_id=${encodeURIComponent(chapterId)}`)
  if (conversationId) q.push(`conversation_id=${encodeURIComponent(conversationId)}`)
  const qs = q.length ? `?${q.join('')}` : ''
  return http.get(`/projects/${projectId}/discussion${qs}`)
}

// 手动追加一条消息（闲聊、不调模型）
export function discussionAppend(projectId, payload, chapterId, conversationId) {
  const q = []
  if (chapterId) q.push(`chapter_id=${encodeURIComponent(chapterId)}`)
  if (conversationId) q.push(`conversation_id=${encodeURIComponent(conversationId)}`)
  const qs = q.length ? `?${q.join('')}` : ''
  return http.post(`/projects/${projectId}/discussion/messages${qs}`, payload)
}

// 清空当前商讨缓存；线程优先级：conversationId > chapter_id > 小说级默认线程
export function discussionClear(projectId, chapterId, conversationId) {
  const q = []
  if (chapterId) q.push(`chapter_id=${encodeURIComponent(chapterId)}`)
  if (conversationId) q.push(`conversation_id=${encodeURIComponent(conversationId)}`)
  const qs = q.length ? `?${q.join('')}` : ''
  return http.delete(`/projects/${projectId}/discussion${qs}`)
}

// 将当前草稿归档为指定章节备注
export function discussionArchive(projectId, chapterId, conversationId) {
  const q = [`chapter_id=${encodeURIComponent(chapterId)}`]
  if (conversationId) q.push(`conversation_id=${encodeURIComponent(conversationId)}`)
  return http.post(`/projects/${projectId}/discussion/archive?${q.join('')}`)
}
