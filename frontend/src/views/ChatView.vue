<template>
  <div class="cv">
    <!-- 欢迎态：截图形态。无任何上下文时显示，大输入框 + 三按钮 + 三条提示 -->
    <div v-if="isWelcome" class="cv-welcome">
      <h1 class="cv-hero-title">你好，欢迎来到智能网页小说</h1>
      <h2 class="cv-hero-sub">你可以对话探讨小说剧情</h2>
      <h2 class="cv-hero-sub">或者选择小说进行创作</h2>

      <!-- 大输入框 + 右侧「发送」按钮 -->
      <div class="cv-compose">
        <textarea
          v-model="welcomeText"
          class="cv-compose-input"
          rows="4"
          placeholder="可以聊聊角色动机、剧情走向、章节瓶颈……也可以让我帮你思考设定"
          @keydown.ctrl.enter.prevent="onWelcomeSend"
        />
        <button class="cv-send-btn" :disabled="!welcomeText.trim()" @click="onWelcomeSend">
          发送
        </button>
      </div>

      <!-- 三按钮：选择小说 / 选择模型 / 思考模式 -->
      <div class="cv-options">
        <div class="cv-opt">
          <el-select
            v-model="store.currentNovelId"
            placeholder="选择小说"
            size="default"
            style="width: 180px"
            @change="onSelectNovel"
          >
            <el-option
              v-for="n in store.novels"
              :key="n.id"
              :label="n.name"
              :value="n.id"
            />
          </el-select>
          <p class="cv-tip">不选小说默认是对话</p>
        </div>
        <div class="cv-opt">
          <el-select
            v-model="store.currentModelId"
            placeholder="选择模型"
            size="default"
            style="width: 180px"
            @change="store.selectModel"
          >
            <el-option
              v-for="m in store.models"
              :key="m.id"
              :label="m.name"
              :value="m.id"
            />
          </el-select>
          <p class="cv-tip">无默认模型时回退到首个</p>
        </div>
        <div class="cv-opt">
          <el-switch v-model="enableThinking" />
          <span class="cv-opt-label">思考模式</span>
          <p class="cv-tip">开启后展示模型推理过程（耗 token）</p>
        </div>
      </div>

      <!-- 上下文提示：当前会话尚未绑定小说 / 模型时的红字提醒 -->
      <div class="cv-banner">
        <div v-if="!store.currentNovelId" class="cv-banner-item">
          <el-icon><Warning /></el-icon>
          <span>未选小说——发送不会进入任何商讨，可选一本 / 让对话漫游</span>
        </div>
        <div v-if="store.currentNovelId && !store.currentChapterId" class="cv-banner-item is-info">
          <el-icon><InfoFilled /></el-icon>
          <span>当前在「{{ store.currentNovel?.name }}」项目级讨论（未锁定到具体章节）</span>
        </div>
      </div>
    </div>

    <!-- 活跃态：常规聊天（已选好上下文、有历史时） -->
    <el-container v-else class="cv-active" direction="vertical">
      <div class="cv-toolbar">
        <span class="cv-title">当前对话：{{ chatTitle }}</span>
        <el-tag v-if="store.currentChapterId" type="warning" size="small" effect="plain">
          章级线程
        </el-tag>
        <el-tag v-else-if="store.currentConversationId" type="success" size="small" effect="plain">
          对话·{{ convTitle }}
        </el-tag>
        <el-tag v-else-if="store.currentNovelId" type="info" size="small" effect="plain">
          小说级
        </el-tag>
        <div class="cv-spacer" />
        <el-button size="small" @click="onResetToWelcome">新建对话</el-button>
      </div>

      <el-main class="cv-chat">
        <ChatPanel :messages="messages" @pick-direction="onPickDirection" @confirm-entities="onConfirmEntities" />
      </el-main>

      <el-footer class="cv-input" height="auto">
        <ChatInput />
      </el-footer>
    </el-container>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Warning, InfoFilled } from '@element-plus/icons-vue'
import { useProjectStore } from '@/store/project'
import { memoryApi } from '@/api/assist'
import ChatPanel from '@/components/workspace/ChatPanel.vue'
import ChatInput from '@/components/workspace/ChatInput.vue'

const store = useProjectStore()
const welcomeText = ref('')
const enableThinking = ref(false)

// 标题：选章时显示「《小说》· 章名」，对话级显示 「对话·时间戳」，否则仅显示小说名
const chatTitle = computed(() => {
  const novel = store.currentNovel?.name || '未选择小说'
  const ch = store.currentChapter
  if (ch) return `《${novel}》· ${ch.title || `第${ch.chapter_no}章`}`
  if (store.currentConversationId) {
    return `《${novel}》· 对话·${convTitle.value}`
  }
  return novel
})
const convTitle = computed(() => {
  const c = store.conversations.find((x) => x.id === store.currentConversationId)
  return c?.title || ''
})

// 欢迎态判定：无任何上下文（无小说 / 无章 / 无对话 / 无历史消息）
const isWelcome = computed(() => {
  return (
    !store.currentNovelId &&
    !store.currentChapterId &&
    !store.currentConversationId &&
    (store.discussionMessages?.length || 0) === 0
  )
})

// 侧栏「新建小说」按钮触发后，新小说被选中也应立即切到活跃态
const onSelectNovel = (id) => {
  store.selectNovel(id)
}

const onWelcomeSend = async () => {
  const text = welcomeText.value.trim()
  if (!text) return
  if (!store.currentNovelId) {
    // 没选小说：先创建一个「漫游对话」会话，确保独享记忆
    const conv = store.addConversation('')
    ElMessage.info('未选小说，对话会保留在「' + conv.title + '」里漫游')
    return store.sendDiscussion(text, enableThinking.value)
  }
  // 选了小说：首次发送视为进入该小说的商讨
  if (!store.currentConversationId) {
    store.addConversation(store.currentNovelId)
  }
  welcomeText.value = ''
  await store.sendDiscussion(text, enableThinking.value)
}

// 点走向卡片 = 把这条方向作为下一章的共识发进商讨。
// 走消息而不是直接改章节要点，是为了留痕——作者事后能看到当初为什么这么写。
// 附加行为：若当前正处在「第 N 章」的章级上下文，且第 N+1 章已存在，则自动切到
// 下一章再发——否则这条方向会落在第 N 章的线程里，而作者真正要写的是第 N+1 章
// （问题 2.3 根因：走向卡片点了，消息却进了旧章，作者还得手动再切一次）。
const onPickDirection = async (d) => {
  const text = `就按这个方向走：${d.title}。${d.detail || ''}`
  const cur = store.currentChapter
  if (cur) {
    const next = findNextChapter(cur)
    if (next && next.id !== store.currentChapterId) {
      store.selectChapter(next.id)
      ElMessage.info(`已切到第 ${next.chapter_no} 章，方向已写入该章商讨`)
    }
  }
  await store.sendDiscussion(text, enableThinking.value)
}

// 在 4 级结构里按 chapter_no 找当前章的下一章（同篇优先，跨篇继续向后找）
const findNextChapter = (cur) => {
  let best = null
  for (const v of store.structure.volumes || []) {
    for (const a of v.articles || []) {
      for (const c of a.chapters || []) {
        if (c.id === cur.id) continue
        if ((c.chapter_no || 0) <= (cur.chapter_no || 0)) continue
        if (!best || (c.chapter_no || 0) < (best.chapter_no || 0)) best = c
      }
    }
  }
  return best
}

// AI 在对话中识别到的新角色/势力/地点 → 一键确认写进资料库。
// 写库走后端 confirm_entities（含重名跳过），不依赖 AI 自己声称"已添加"。
const onConfirmEntities = async (m) => {
  if (!store.currentNovelId) {
    ElMessage.warning('请先选择一本小说，才能把设定写入它的资料库')
    return
  }
  m.meta.confirming = true
  try {
    const res = await memoryApi.confirmEntities(
      store.currentNovelId,
      store.currentChapterId || null,
      m.meta.items,
    )
    const { created = [], skipped = [] } = res || {}
    let tip = `已写入 ${created.length} 条`
    if (skipped.length) tip += `，跳过 ${skipped.length} 条（${skipped.map((s) => s.reason).join('、')}）`
    m.meta.confirmed = true
    ElMessage.success(tip)
  } catch (e) {
    ElMessage.error('写入失败：' + (e?.response?.data?.detail || e?.message || '未知错误'))
  } finally {
    m.meta.confirming = false
  }
}

// 「新建对话」按钮：真正开一个独立会话线程（不再只是擦干净屏幕）。
// 切到新会话后由 watch(currentConversationId) 自动 loadDiscussion 显示空线程。
const onResetToWelcome = () => {
  const conv = store.addConversation(store.currentNovelId || '')
  ElMessage.success(`已新建对话「${conv.title}」`)
}

onMounted(async () => {
  store.hydrateConversations()   // 恢复侧栏会话列表（来自 localStorage），刷新后仍在
  await store.loadNovels()
  store.loadModels()
  // 刻意不在此恢复 currentNovelId / currentConversationId：
  // 否则欢迎页（落地页）会被立刻翻掉、一闪而过跳进某本小说。
  // 历史已落库（按 conversation_id），点侧栏会话即带完整 DB 历史进入，无需自动跳入。
  // ★ 仅在有上下文时加载讨论记录，避免无条件拉全局历史导致欢迎页被覆盖
  if (store.currentNovelId || store.currentChapterId || store.currentConversationId) {
    await store.loadDiscussion()
  }
})

watch(
  () => store.currentChapterId,
  () => store.loadDiscussion(),
)
watch(
  () => store.currentConversationId,
  () => store.loadDiscussion(),
)

const messages = computed(() => store.discussionMessages)
</script>

<style scoped>
.cv { height: 100%; display: flex; flex-direction: column; }
.cv-spacer { flex: 1; }

/* —— 欢迎态 ——————————————————————————————————————— */
.cv-welcome {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 24px;
  text-align: center;
  background: #fff;
}
.cv-hero-title {
  font-size: 32px;
  font-weight: 700;
  color: #303133;
  margin: 0 0 12px;
}
.cv-hero-sub {
  font-size: 18px;
  font-weight: 500;
  color: #606266;
  margin: 4px 0;
}

/* 大输入框 + 右侧发送按钮 —— 仿截图蓝色卡片 */
.cv-compose {
  margin: 28px 0 12px;
  width: min(680px, 90%);
  display: flex;
  gap: 12px;
  align-items: stretch;
}
.cv-compose-input {
  flex: 1;
  border-radius: 12px;
  border: 2px solid #409eff;
  background: #e6f4ff;
  padding: 14px 18px;
  font-size: 15px;
  line-height: 1.6;
  resize: none;
  outline: none;
  color: #303133;
  transition: border-color .15s, background .15s;
}
.cv-compose-input:focus {
  border-color: #1f7cdc;
  background: #f0f8ff;
}
.cv-send-btn {
  width: 80px;
  border-radius: 12px;
  border: none;
  background: #409eff;
  color: #fff;
  font-weight: 600;
  cursor: pointer;
  font-size: 15px;
  transition: background .15s;
}
.cv-send-btn:hover:not(:disabled) { background: #1f7cdc; }
.cv-send-btn:disabled { background: #a0cfff; cursor: not-allowed; }

/* 三按钮行：选择小说 / 选择模型 / 思考模式 */
.cv-options {
  display: flex;
  justify-content: center;
  gap: 32px;
  margin-top: 18px;
  flex-wrap: wrap;
}
.cv-opt {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.cv-opt-label {
  font-size: 13px;
  color: #606266;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.cv-tip {
  margin: 0;
  font-size: 11px;
  color: #909399;
  line-height: 1.4;
  max-width: 180px;
  text-align: center;
}

/* 上下文提示横幅 */
.cv-banner {
  margin-top: 28px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
}
.cv-banner-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: #fff3f3;
  color: #d94545;
  padding: 6px 14px;
  border-radius: 4px;
  font-size: 13px;
}
.cv-banner-item.is-info {
  background: #e6f4ff;
  color: #1f7cdc;
}

/* —— 活跃态 ——————————————————————————————————————— */
.cv-active { height: 100%; }
.cv-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 4px 12px;
}
.cv-title { font-weight: 600; }
.cv-chat { padding: 0; overflow: hidden; }
.cv-input { padding: 0; background: transparent; }
</style>
