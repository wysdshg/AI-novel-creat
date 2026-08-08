import { defineStore, acceptHMRUpdate } from 'pinia'
import { projectApi } from '@/api/projects'
import { modelApi } from '@/api/model'
import { discussionChatStream, discussionLoad, discussionClear } from '@/api/discussion'

// 全局作品/对话/模型选择状态。
// 作品列表现在由后端 /api/v1/projects 提供（已持久化），
// 模型列表由后端 /api/v1/models 提供（已真实持久化，可在「模型配置」中增删改查）。
export const useProjectStore = defineStore('project', {
  state: () => ({
    // 作品列表（来自后端，每个作品含 dialogues 作为前端本地会话概念，初始为空）
    novels: [],
    loaded: false,
    // 可用模型（来自模型配置，后端接口 GET /api/v1/models）
    models: [],
    currentNovelId: '',
    currentDialogueId: '',
    currentModelId: '',
    // 当前小说的剧情商讨消息（user/ai），由 ChatView 展示、ChatInput 发送共享
    discussionMessages: [],
    sendingDiscussion: false,
  }),
  getters: {
    currentNovel: (s) => s.novels.find((n) => n.id === s.currentNovelId) || null,
    currentDialogue: (s) => {
      const n = s.novels.find((x) => x.id === s.currentNovelId)
      return n ? n.dialogues.find((d) => d.id === s.currentDialogueId) : null
    },
    currentModel: (s) => s.models.find((m) => m.id === s.currentModelId) || null,
  },
  actions: {
    // 拉取作品列表（应用启动时调用一次）
    async loadNovels() {
      const res = await projectApi.list()
      this.novels = (res.items || []).map((p) => ({
        id: p.id,
        name: p.name,
        genre: p.genre,
        summary: p.summary,
        status: p.status,
        chapterCount: p.chapter_count || 0,
        dialogues: [],
      }))
      this.loaded = true
      if (!this.novels.find((n) => n.id === this.currentNovelId)) {
        this.currentNovelId = this.novels.length ? this.novels[0].id : ''
        this.currentDialogueId = ''
      }
    },
    // 拉取模型配置列表，并默认选中「默认模型」；无默认则选第一个
    async loadModels() {
      try {
        const res = await modelApi.list()
        const list = Array.isArray(res) ? res : (res.items || [])
        this.models = list
        const def = list.find((m) => m.is_default) || list[0]
        if (def) this.currentModelId = def.id
      } catch (e) {
        console.error('加载模型列表失败', e)
      }
    },
    // 新建小说成功后并入列表（不重复请求）
    addNovel(novel) {
      if (this.novels.find((n) => n.id === novel.id)) return
      this.novels.unshift({
        id: novel.id,
        name: novel.name,
        genre: novel.genre,
        summary: novel.summary,
        status: novel.status,
        chapterCount: novel.chapter_count || 0,
        dialogues: [],
      })
    },
    selectNovel(id) {
      this.currentNovelId = id
      this.currentDialogueId = ''
      this.discussionMessages = []
      // 切换小说时，从后端加载已持久化的商讨缓存
      this.loadDiscussion()
    },
    // 从后端加载当前小说的商讨记录（持久化缓存），映射到前端消息结构
    async loadDiscussion() {
      if (!this.currentNovelId) {
        this.discussionMessages = []
        return
      }
      try {
        const res = await discussionLoad(this.currentNovelId)
        const list = Array.isArray(res) ? res : (res?.items || [])
        this.discussionMessages = (list || []).map((m) => ({
          id: m.id,
          role: m.role || 'user',
          content: m.content || '',
          thinking: m.thinking || '',
          created_at: m.created_at,
        }))
      } catch (e) {
        console.error('加载商讨记录失败', e)
      }
    },
    // 清空当前商讨缓存（前端 + 后端同步）
    async clearDiscussion() {
      if (!this.currentNovelId) return
      try {
        await discussionClear(this.currentNovelId)
      } catch (e) {
        console.error('清空商讨记录失败', e)
      }
      this.discussionMessages = []
    },
    // 发送一条商讨消息并流式获取 AI 回复
    async sendDiscussion(userText, enableThinking) {
      if (!this.currentNovelId) return
      if (this.sendingDiscussion) return
      if (!userText || !userText.trim()) return

      this.discussionMessages.push({ role: 'user', content: userText.trim() })
      this.discussionMessages.push({ role: 'ai', content: '', thinking: '' })
      const aiIndex = this.discussionMessages.length - 1

      const history = this.discussionMessages
        .slice(0, aiIndex)
        .map((m) => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.content }))

      this.sendingDiscussion = true
      try {
        await discussionChatStream(
          this.currentNovelId,
          { messages: history, enable_thinking: enableThinking },
          (event, data) => {
            const current = this.discussionMessages[aiIndex]
            if (event === 'chunk') {
              this.discussionMessages.splice(aiIndex, 1, {
                ...current,
                content: current.content + (data.text || ''),
              })
            } else if (event === 'thinking') {
              this.discussionMessages.splice(aiIndex, 1, {
                ...current,
                thinking: current.thinking + (data.text || ''),
              })
            }
          },
        )
      } catch (e) {
        this.discussionMessages[aiIndex].content += `\n[发送失败：${e?.message || e}]`
      } finally {
        this.sendingDiscussion = false
      }
    },
    selectDialogue(id) { this.currentDialogueId = id },
    selectModel(id) { this.currentModelId = id },
    // 删除小说：调后端 DELETE，成功后从列表移除；
    // 若被删的是当前选中作品，自动回退到列表第一项。
    async deleteNovel(id) {
      await projectApi.remove(id)
      this.novels = this.novels.filter((n) => n.id !== id)
      if (this.currentNovelId === id) {
        this.currentNovelId = this.novels.length ? this.novels[0].id : ''
        this.currentDialogueId = ''
      }
    },
  },
})

// 开发期 HMR：修改本 store 时自动热替换实例，避免 Vite 不重载 Pinia 导致
// `store.xxx is not a function` 之类报错（无需重启 dev server）。
if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useProjectStore, import.meta.hot))
}
