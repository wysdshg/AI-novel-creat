// 模块3：剧情商讨（需求 6）。
import http from './http'
import { readSseStream } from '@/utils/sse'

// 流式对话（SSE，使用 fetch 直接读流）
// 支持外部传入 { signal } 实现手动停止；中止后抛 name='GenerationStopped' 的错误，
// 便于调用方与「网络/超时」错误区分开（否则中止会被当成失败弹红字）。
export async function discussionChatStream(projectId, body, onEvent, chapterId, { signal } = {}) {
  const q = chapterId ? `?chapter_id=${encodeURIComponent(chapterId)}` : ''
  // 注意：此处曾有 console.group 打印完整 Body / 最后一条用户消息正文 / system prompt。
  // 属隐私泄漏（用户输入全文进控制台），已移除（问题 1.1）。排查时只打无内容信息（条数/开关）。
  const resp = await fetch(`/api/v1/projects/${projectId}/discussion/chat${q}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  // 状态校验 / 超时 / 中止 / 畸形帧容忍统一在 readSseStream（Phase 3.3 抽公共实现）
  await readSseStream(resp, onEvent, { signal, errorPrefix: '商讨接口' })
}

// 全局对话（无需选择小说，类似豆包/ChatGPT 通用助手模式）
// 注入全局设定库 + 全局 SKILL，不含任何小说数据
export async function discussionGlobalChatStream(body, onEvent, { signal } = {}) {
  // 注意：此处曾有 console.group 打印完整 Body / 最后一条用户消息正文，属隐私泄漏，
  // 已移除（问题 1.1）。
  const resp = await fetch('/api/v1/discussion/global-chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  await readSseStream(resp, onEvent, { signal, errorPrefix: '全局对话接口' })
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
