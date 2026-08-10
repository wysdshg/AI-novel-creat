import { defineStore, acceptHMRUpdate } from 'pinia'
import { projectApi } from '@/api/projects'
import { modelApi } from '@/api/model'
import { discussionChatStream, discussionGlobalChatStream, discussionLoad, discussionClear, discussionAppend } from '@/api/discussion'
import { volumeApi } from '@/api/volume'
import { articleApi } from '@/api/article'
import { chapterApi } from '@/api/chapter'

// 未选小说时的「全局对话」线程所用的保留 project_id，与后端
// app/services/reference_crud.py::GLOBAL_PROJECT_ID 保持一致。
const GLOBAL_PROJECT_ID = '__global__'

// 全局作品/对话/模型/4 级结构 选择状态。
// 4 级结构：小说 → 卷(volume) → 篇(article) → 章(chapter)。
// 选小说 → 加载结构；选章 → 加载该章对话历史（ChatView 接管，第 2 批后续）。
export const useProjectStore = defineStore('project', {
  state: () => ({
    // 作品列表（来自后端）
    novels: [],
    loaded: false,
    // 可用模型
    models: [],
    currentNovelId: '',
    currentChapterId: '',
    currentModelId: '',
    // 4 级结构（当前小说）：volumes[].articles[].chapters[]
    structure: { volumes: [] },
    structureLoaded: false,
    // 当前小说的剧情商讨消息（user/ai），由 ChatView 展示、ChatInput 发送共享
    discussionMessages: [],
    sendingDiscussion: false,
    // 「豆包式」对话会话：UI 维度——独立记忆的占位，localStorage 持久化。
    // 每个会话记录 { id, title, novelId, createdAt }；
    // 当前会话 id 为 '' 表示「未进入」→ ChatView 走欢迎态。
    _currentVolumeId: '',
    _currentArticleId: '',
    currentConversationId: '',
    conversations: [],
  }),
  getters: {
    currentNovel: (s) => s.novels.find((n) => n.id === s.currentNovelId) || null,
    currentModel: (s) => s.models.find((m) => m.id === s.currentModelId) || null,
    currentVolume: (s) => {
      const v = s.structure.volumes.find((x) => x.id === s._currentVolumeId)
      return v || null
    },
    currentArticle: (s) => {
      const v = s.currentVolume
      if (!v) return null
      return v.articles.find((a) => a.id === s._currentArticleId) || null
    },
    // 章可能在任意卷/篇下——直接按 id 找，避免父级未点过时标题退化
    currentChapter: (s) => {
      for (const v of s.structure.volumes || []) {
        for (const a of v.articles || []) {
          const c = (a.chapters || []).find((x) => x.id === s.currentChapterId)
          if (c) return c
        }
      }
      return null
    },
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
      }))
      this.loaded = true
      // 注意：不再自动选中第一本小说。否则进入网站会跳过欢迎页、直接跳到某本小说的
      // 项目级讨论（currentNovelId 被设上 → ChatView.isWelcome 变 false）。
      // 小说 / 对话需由用户在侧栏或欢迎页显式选择才进入；未选时 ChatView 显示欢迎态。
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
      })
    },
    selectNovel(id) {
      this.currentNovelId = id
      this.resetStructureState()
      this.loadStructure().catch(() => {})
      // 进入小说级讨论：确保有一个会话线程（恢复最近一个 / 新建），
      // 否则所有对话会写进「小说级默认线程」、互相串台。
      this.ensureConversation(id)
      this.loadDiscussion()
      this._saveActiveToStorage()
    },
    // —— 4 级结构相关 ——
    resetStructureState() {
      this.currentChapterId = ''
      this._currentVolumeId = ''
      this._currentArticleId = ''
      this.structure = { volumes: [] }
      this.structureLoaded = false
    },
    async loadStructure(projectId) {
      const pid = projectId || this.currentNovelId
      if (!pid) {
        this.structure = { volumes: [] }
        this.structureLoaded = false
        return
      }
      try {
        const volumes = (await volumeApi.list(pid)) || []
        // 拉每卷下的篇，再拉每篇下的章
        for (const v of volumes) {
          const articles = (await articleApi.list(pid, { volume_id: v.id })) || []
          for (const a of articles) {
            const chapters = (await articleApi.listChapters(a.id)) || []
            a.chapters = chapters
          }
          v.articles = articles
        }
        this.structure = { volumes }
        this.structureLoaded = true
      } catch (e) {
        console.error('加载 4 级结构失败', e)
        this.structure = { volumes: [] }
        this.structureLoaded = false
      }
    },
    selectVolume(id) {
      this._currentVolumeId = id
      this._currentArticleId = ''
      this.currentChapterId = ''
    },
    selectArticle(id) {
      this._currentArticleId = id
      this.currentChapterId = ''
    },
    selectChapter(id) {
      this.currentChapterId = id
      // 清空会话 ID：进入章线程后，不再使用小说级会话线程（避免读写不对称）
      this.currentConversationId = ''
      // 根因修复：直接进入某章时，也要把所属卷/篇设为当前导航状态，
      // 否则 currentArticle / currentVolume 为 null，生成章节会因缺少 article_id
      // 而沦为「孤儿章」（不挂在任何篇下、侧栏树不显示）。
      const ch = this.currentChapter
      if (ch?.article_id) {
        this._currentArticleId = ch.article_id
      }
      // 从结构里定位父卷/父篇，补全导航状态
      for (const v of this.structure.volumes || []) {
        for (const a of v.articles || []) {
          if (a.id === this._currentArticleId || (a.chapters || []).some((c) => c.id === id)) {
            this._currentVolumeId = v.id
            if (a.id !== this._currentArticleId) this._currentArticleId = a.id
            break
          }
        }
      }
      // 进入该章对话：加载该章独立的商讨线程（有历史）
      this.loadDiscussion()
      this._saveActiveToStorage()
    },
    // 删除小说：调后端 DELETE，成功后从列表移除；
    // 若被删的是当前选中作品，自动回退到列表第一项。
    async deleteNovel(id) {
      await projectApi.remove(id)
      this.novels = this.novels.filter((n) => n.id !== id)
      if (this.currentNovelId === id) {
        this.currentNovelId = this.novels.length ? this.novels[0].id : ''
        this.resetStructureState()
        this._saveActiveToStorage()
      }
    },
    // 清空当前商讨缓存（前端 + 后端同步）。章级上下文时清章线程，否则清当前会话线程。
    async clearDiscussion() {
      // 未选小说 → 清全局线程；否则按 章线程 / 会话线程 清
      const isGlobal = !this.currentNovelId
      const projectId = isGlobal ? GLOBAL_PROJECT_ID : this.currentNovelId
      const chapterId = isGlobal ? null : (this.currentChapterId || null)
      const conversationId = isGlobal ? null : (chapterId ? null : (this.currentConversationId || null))
      try {
        await discussionClear(projectId, chapterId, conversationId)
      } catch (e) {
        console.error('清空商讨记录失败', e)
      }
      this.discussionMessages = []
    },
    // 持久化一条本地消息到后端商讨缓存（配置/slash 指令结果不调模型，但也要落库，
    // 否则重载后「/角色 /地点」等配置语句会消失）。线程与当前上下文一致：
    // 章级上下文 → 落章线程（conversation_id=null）；小说级 → 落当前会话线程。
    async appendPersistedMessage(role, content, meta = null) {
      if (!this.currentNovelId) return
      if (!content || !content.trim()) return
      const backendRole = role === 'ai' ? 'assistant' : 'user'
      const conversationId = this.currentChapterId ? null : (this.currentConversationId || null)
      try {
        await discussionAppend(
          this.currentNovelId,
          { role: backendRole, content, meta },
          this.currentChapterId,
          conversationId,
        )
      } catch (e) {
        console.error('持久化本地消息失败', e)
      }
    },
    // 发送一条商讨消息并流式获取 AI 回复
    async sendDiscussion(userText, enableThinking) {
      if (this.sendingDiscussion) return
      if (!userText || !userText.trim()) return

      console.group('📤 [Store] sendDiscussion 调用')
      console.log('用户输入:', userText)
      console.log('当前小说ID:', this.currentNovelId)
      console.log('当前章节ID:', this.currentChapterId)
      console.log('当前会话ID:', this.currentConversationId)
      console.log('当前模型ID:', this.currentModelId)
      console.log('enableThinking:', enableThinking)
      console.log('当前消息数(发送前):', this.discussionMessages.length)
      console.groupEnd()

      // === 全局模式（未选小说且未选章节）→ 走全局对话端点 ===
      // ★ 收紧条件：有 chapterId 但无 novelId 是异常状态（不应走全局）
      if (!this.currentNovelId && !this.currentChapterId) {
        this.discussionMessages.push({ role: 'user', content: userText.trim() })
        this.discussionMessages.push({ role: 'ai', content: '', thinking: '' })
        const aiIndex = this.discussionMessages.length - 1

        const history = this.discussionMessages
          .slice(0, aiIndex)
          .map((m) => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.content }))

        this.sendingDiscussion = true
        try {
          await discussionGlobalChatStream(
            { messages: history, enable_thinking: enableThinking, model_id: this.currentModelId || undefined },
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
              if (event === 'done' && this.sendingDiscussion) {
                this.sendingDiscussion = false
              }
            },
          )
        } catch (e) {
          this.discussionMessages[aiIndex].content += `\n[发送失败：${e?.message || e}]`
        } finally {
          this.sendingDiscussion = false
        }
        return
      }

      // === 小说模式（已选小说）→ 走原有商讨链路 ===
      // 小说级上下文但还没绑定会话时，先建一个，确保消息落进独立线程
      if (!this.currentChapterId && !this.currentConversationId) {
        this.ensureConversation(this.currentNovelId)
      }

      this.discussionMessages.push({ role: 'user', content: userText.trim() })
      this.discussionMessages.push({ role: 'ai', content: '', thinking: '' })
      const aiIndex = this.discussionMessages.length - 1

      const history = this.discussionMessages
        .slice(0, aiIndex)
        .map((m) => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.content }))

      // 章级上下文 → conversation_id 传 null（走章线程）；小说级 → 传当前会话 id
      const conversationId = this.currentChapterId ? null : (this.currentConversationId || null)

      console.group('📤 [Store] 小说模式 — 构建请求体')
      console.log('history 条数:', history.length)
      history.forEach((m, i) => {
        const preview = (m.content || '').slice(0, 120)
        console.log(`  [${i}] ${m.role}: ${preview}${m.content?.length > 120 ? '...' : ''}`)
      })
      console.log('conversationId:', conversationId)
      console.groupEnd()

      this.sendingDiscussion = true
      try {
        await discussionChatStream(
          this.currentNovelId,
          { messages: history, enable_thinking: enableThinking, conversation_id: conversationId, model_id: this.currentModelId || undefined },
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
            } else if (event === 'entity_suggestion') {
              // AI 在对话中识别出新实体，插入一张「确认写入」卡片
              this.discussionMessages.push({
                role: 'ai',
                content: '',
                thinking: '',
                meta: { type: 'entity_suggestion', items: data.items || [] },
                type: 'entity_suggestion',
              })
            }
            // 'done' 事件由后端 finally 块保证发送，收到后可提前重置状态
            if (event === 'done' && this.sendingDiscussion) {
              this.sendingDiscussion = false
            }
          },
          this.currentChapterId,
        )
      } catch (e) {
        this.discussionMessages[aiIndex].content += `\n[发送失败：${e?.message || e}]`
      } finally {
        this.sendingDiscussion = false
      }
    },
    // 从后端加载当前线程的商讨记录（持久化缓存），映射到前端消息结构。
    // 线程优先级：conversationId > chapterId > 小说级默认线程。
    // ★ 关键：写入侧（sendDiscussion）在有 chapterId 时强制 conversationId=null，
    //   读取侧必须对称——否则写进章桶、从会话桶读，消息必然丢失。
    async loadDiscussion(chapterId = this.currentChapterId, conversationId = this.currentConversationId) {
      // 未选小说 → 加载全局线程历史（豆包式通用对话也要有记忆）
      const isGlobal = !this.currentNovelId
      const projectId = isGlobal ? GLOBAL_PROJECT_ID : this.currentNovelId
      if (isGlobal) {
        chapterId = null
        conversationId = null
      } else if (chapterId) {
        // 章级模式：强制清空 conversationId，与写入侧对称
        conversationId = null
      }
      try {
        const res = await discussionLoad(projectId, chapterId, conversationId)
        const list = Array.isArray(res) ? res : (res?.items || [])
        this.discussionMessages = (list || []).map((m) => ({
          id: m.id,
          role: m.role || 'user',
          content: m.content || '',
          thinking: m.thinking || '',
          // meta.type === 'post_chapter_directions' 时前端渲染成走向卡片而非纯文本
          meta: m.meta || {},
          type: m.type || 'text',
          created_at: m.created_at,
        }))
      } catch (e) {
        console.error('加载商讨记录失败', e)
      }
    },
    // —— 豆包式「对话会话」UI 状态（localStorage 持久化，前后端 1:1 共存即可）——
    _loadConversationsFromStorage() {
      try {
        const raw = localStorage.getItem('na_conversations')
        if (!raw) return []
        const arr = JSON.parse(raw)
        return Array.isArray(arr) ? arr : []
      } catch {
        return []
      }
    },
    _saveConversationsToStorage() {
      try {
        localStorage.setItem('na_conversations', JSON.stringify(this.conversations || []))
      } catch (e) {
        console.error('保存对话列表失败', e)
      }
    },
    // 启动时调一次：把 localStorage 中的会话列表恢复到 store
    hydrateConversations() {
      this.conversations = this._loadConversationsFromStorage()
    },
    // 「新建对话」：时间戳为标题（截图样式 8-7-12-00），建立独立会话线程并进入活跃态。
    // 注意：不再调用 selectNovel（否则会递归：selectNovel→ensureConversation→addConversation）。
    addConversation(novelId = '') {
      const now = new Date()
      const m = now.getMonth() + 1
      const d = now.getDate()
      const H = now.getHours()
      const M = String(now.getMinutes()).padStart(2, '0')
      const title = `${m}-${d}-${H}-${M}`
      const item = {
        id: 'cv-' + now.getTime().toString(36) + Math.floor(Math.random() * 1e6).toString(36),
        title,
        novelId,
        createdAt: now.toISOString(),
      }
      this.conversations.unshift(item)
      this._saveConversationsToStorage()
      this.currentConversationId = item.id
      if (novelId) this.currentNovelId = novelId
      this.currentChapterId = '' // 会话是小说级线程，进入会话即离开章线程
      this._saveActiveToStorage()
      return item
    },
    selectConversation(id) {
      const conv = this.conversations.find((c) => c.id === id)
      this.currentConversationId = id
      // 该会话绑过小说 → 切到对应小说并离开章线程；不绑则保持当前小说不动
      if (conv && conv.novelId) {
        this.currentNovelId = conv.novelId
        this.currentChapterId = ''
      }
      this._saveActiveToStorage()
      this.loadDiscussion()
    },
    // 确保小说级上下文存在一个会话线程：已有则复用最近一个，否则新建。
    // 仅在「非章级上下文」且「尚未绑定会话」时生效，避免覆盖用户已选会话。
    ensureConversation(novelId) {
      if (this.currentChapterId) return
      if (this.currentConversationId) return
      const existing = this.conversations.find((c) => c.novelId === novelId)
      if (existing) {
        this.currentConversationId = existing.id
      } else {
        this.addConversation(novelId)
      }
    },
    removeConversation(id) {
      const wasActive = this.currentConversationId === id
      this.conversations = this.conversations.filter((c) => c.id !== id)
      this._saveConversationsToStorage()
      if (wasActive) {
        this.currentConversationId = ''
        this.discussionMessages = []
        // 删的是当前会话 → 自动开一个空会话，避免回到「无线程」状态
        if (this.currentNovelId) this.ensureConversation(this.currentNovelId)
      }
      this._saveActiveToStorage()
      // 一并删除该会话在数据库中的消息，避免孤儿数据
      if (this.currentNovelId) {
        discussionClear(this.currentNovelId, null, id).catch((e) =>
          console.error('删除会话消息失败', e),
        )
      }
    },
    // —— 活跃上下文（小说 + 会话）持久化，刷新后自动恢复并加载历史 ——
    _saveActiveToStorage() {
      try {
        localStorage.setItem(
          'na_active',
          JSON.stringify({ novelId: this.currentNovelId, conversationId: this.currentConversationId }),
        )
      } catch (e) {
        console.error('保存活跃上下文失败', e)
      }
    },
  },
})

// 开发期 HMR：修改本 store 时自动热替换实例，避免 Vite 不重载 Pinia 导致
// `store.xxx is not a function` 之类报错（无需重启 dev server）。
if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useProjectStore, import.meta.hot))
}
