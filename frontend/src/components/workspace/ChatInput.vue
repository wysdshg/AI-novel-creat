<template>
  <div class="ci">
    <!-- 快捷指令工具栏 -->
    <div class="ci-quick">
      <span class="ci-quick-label">快捷：</span>
      <el-tag
        v-for="q in quick"
        :key="q"
        class="ci-chip"
        effect="plain"
        @click="onQuick(q)"
      >{{ q }}</el-tag>
      <el-button
        class="ci-namegen"
        size="small"
        @click="nameGenVisible = true"
      >💡 起名</el-button>
    </div>

    <el-mention
      ref="mentionsRef"
      v-model="text"
      class="ci-input"
      :options="sortedMentionOptions"
      :prefix="['@']"
      :rows="4"
      resize="none"
      placeholder="输入对话讨论剧情；或用 /角色 /地点 /势力 /设定 直接添加资料，/章节 第5章 要点 直接生成正文"
      @select="onMentionSelect"
    />

    <div class="ci-actions">
      <el-select
        v-model="store.currentNovelId"
        placeholder="选择小说"
        size="small"
        style="width: 150px"
        @change="store.selectNovel"
      >
        <el-option
          v-for="n in store.novels"
          :key="n.id"
          :label="n.name"
          :value="n.id"
        />
      </el-select>

      <el-select
        v-model="store.currentModelId"
        placeholder="选择模型"
        size="small"
        style="width: 170px"
        @change="store.selectModel"
      >
        <el-option
          v-for="m in store.models"
          :key="m.id"
          :label="m.name"
          :value="m.id"
        />
      </el-select>

      <el-tooltip content="关闭后模型不思考，生成更快、更省 token">
        <span class="ci-think">
          <el-switch v-model="enableThinking" size="small" />
          <span class="ci-think-label">思考</span>
        </span>
      </el-tooltip>

      <div class="ci-spacer" />
      <el-button :disabled="store.sendingDiscussion" @click="onClear">清空</el-button>
      <el-button :disabled="store.sendingDiscussion" @click="onSend">
        {{ store.sendingDiscussion ? '回复中…' : '发送' }}
      </el-button>
      <el-tooltip content="请先在左侧选择一篇或一章，再生成章节" :disabled="!!activeArticleId" placement="top">
        <span>
          <el-button type="primary" :disabled="!activeArticleId" @click="onGenerate">生成章节</el-button>
        </span>
      </el-tooltip>
    </div>

    <GenerateChapterDialog
      v-model="genVisible"
      :project-id="store.currentNovelId"
      :article-id="activeArticleId"
      :enable-thinking="enableThinking"
    />

    <NameGeneratorDialog
      v-model="nameGenVisible"
      :project-id="store.currentNovelId"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/store/project'
import { characterApi, factionApi, commandApi } from '@/api/database'
import { generateChapterStream } from '@/api/chapter'
import { parseSlashCommands } from '@/utils/slash'
import GenerateChapterDialog from './GenerateChapterDialog.vue'
import NameGeneratorDialog from './NameGeneratorDialog.vue'

const store = useProjectStore()
const text = ref('')
const genVisible = ref(false)
const nameGenVisible = ref(false)
const mentionsRef = ref(null)
const characters = ref([])
const factions = ref([])
// 思考开关：默认关闭（回复更快、更省 token）；开启后会在回复下方展示模型推理过程。
// 注：章节生成已由后端强制开思考（云端推理模型关思考写长文必复读，见 chapter.py
// NA_CHAPTER_FORCE_THINKING，本地 ollama 除外），此开关只影响聊天展示与本地 ollama。
const enableThinking = ref(false)
// 当前会话中最近被 @ 的条目 ID（按时间先后放入；越后放表示越近使用）
const recentlyMentionedIds = ref([])

// 当前有效的「篇」上下文：优先当前选中的篇，其次当前章所属篇；
// 为空表示还没进入任何篇/章，此时禁止生成章节（避免产出「孤儿章」）。
const activeArticleId = computed(() => {
  if (store.currentArticle?.id) return store.currentArticle.id
  if (store.currentChapter?.article_id) return store.currentChapter.article_id
  return ''
})

const quick = ['@角色', '@势力', '@伏笔', '#生成本章', '#只讨论', '#总结剧情']

// 根据当前小说加载角色库与势力库
async function loadEntities() {
  if (!store.currentNovelId) {
    characters.value = []
    factions.value = []
    return
  }
  try {
    const [cRes, fRes] = await Promise.all([
      characterApi.list(store.currentNovelId),
      factionApi.list(store.currentNovelId),
    ])
    characters.value = Array.isArray(cRes) ? cRes : (cRes.items || [])
    factions.value = Array.isArray(fRes) ? fRes : (fRes.items || [])
  } catch (e) {
    console.error('加载角色/势力列表失败', e)
    characters.value = []
    factions.value = []
  }
}

watch(() => store.currentNovelId, loadEntities, { immediate: true })

// 角色地位优先级：仅主角强制最前，其余同优先级
const ROLE_ORDER = { 主角: 0 }

// 原始 Mention 选项：角色 + 势力
const mentionOptions = computed(() => {
  const charOpts = characters.value.map((c) => ({
    id: c.id,
    type: 'character',
    value: c.name,
    label: `${c.name} · ${c.role_type || '角色'}`,
    roleType: c.role_type,
    updated_at: c.updated_at,
  }))
  const facOpts = factions.value.map((f) => ({
    id: f.id,
    type: 'faction',
    value: f.name,
    label: `${f.name} · 势力`,
    roleType: null,
    updated_at: f.updated_at,
  }))
  return [...charOpts, ...facOpts]
})

const sortedMentionOptions = computed(() => {
  const options = mentionOptions.value
  return [...options].sort((a, b) => {
    // 1. 角色排在势力前面；角色内部主角排最前
    const ra = a.type === 'character' ? (ROLE_ORDER[a.roleType] ?? 1) : 2
    const rb = b.type === 'character' ? (ROLE_ORDER[b.roleType] ?? 1) : 2
    if (ra !== rb) return ra - rb

    // 2. 同组内，最近被 @ 过的置顶（越晚使用越靠前）
    const ia = recentlyMentionedIds.value.indexOf(a.id)
    const ib = recentlyMentionedIds.value.indexOf(b.id)
    if (ia !== -1 && ib !== -1) return ib - ia
    if (ia !== -1) return -1
    if (ib !== -1) return 1

    // 3. 都没最近使用，按 updated_at 倒序（最近编辑过的靠前）
    const ta = a.updated_at ? new Date(a.updated_at).getTime() : 0
    const tb = b.updated_at ? new Date(b.updated_at).getTime() : 0
    if (tb !== ta) return tb - ta
    return a.label.localeCompare(b.label)
  })
})

const onQuick = (q) => {
  if (q === '@角色' || q === '@势力') {
    if (!store.currentNovelId) {
      return ElMessage.warning('请先选择一本小说')
    }
    mentionsRef.value?.focus?.()
    text.value = text.value ? `${text.value} @` : '@'
    return
  }
  text.value = text.value ? `${text.value} ${q} ` : `${q} `
}

const onMentionSelect = (option) => {
  // 记录本次会话的最近使用，靠前的选项优先展示
  recentlyMentionedIds.value = recentlyMentionedIds.value.filter((id) => id !== option.id)
  recentlyMentionedIds.value.push(option.id)
}

const onSend = async () => {
  const content = text.value.trim()
  if (!content) return ElMessage.warning('请输入内容')
  // 未选小说时走全局对话模式（不再拦截，store.sendDiscussion 会自动分流）
  if (store.sendingDiscussion) return

  const actions = parseSlashCommands(content)
  const hasSlash = actions.some((a) => a.kind === 'chapter' || (a.kind === 'config' && a.sub !== '自由'))

  // 没有显式 /指令 时保持原行为：走剧情商讨流
  if (!hasSlash) {
    text.value = ''
    await store.sendDiscussion(content, enableThinking.value)
    return
  }

  // Slash 指令模式：确定性执行配置/生成，不走讨论模型
  text.value = ''
  store.discussionMessages.push({ role: 'user', content })
  // 配置/slash 指令不走 LLM 商讨流（不会经 router 自动落库），需手动持久化，
  // 否则重载后「/角色 /地点」等配置语句会消失。
  await store.appendPersistedMessage('user', content)
  store.sendingDiscussion = true
  try {
    for (const act of actions) {
      if (act.kind === 'config' && act.sub !== '自由') {
        await runConfigCommand(act)
      } else if (act.kind === 'chapter') {
        await runChapterCommand(act)
      }
      // 自由文本在 slash 模式下不额外送入讨论模型，避免与确定性操作混在一起
    }
  } catch (e) {
    store.discussionMessages.push({ role: 'ai', content: '执行失败：' + (e?.message || e) })
  } finally {
    store.sendingDiscussion = false
  }
}

async function runConfigCommand(act) {
  // 单次实体指令（角色/地点/势力）透传 entity_type，让后端只抽该类型，不脑补其他实体
  const entityType = (act.sub === '角色' || act.sub === '地点' || act.sub === '势力') ? act.sub : undefined
  const res = await commandApi.run(store.currentNovelId, {
    text: act.prompt || act.text,
    dry_run: false,
    entity_type: entityType,
  })
  let lines = []
  if (res.reply) lines.push(res.reply)
  const groups = []
  const map = { characters: '角色', factions: '势力', locations: '地点', relations: '关系' }
  for (const [key, label] of Object.entries(map)) {
    const items = res.changes?.[key] || []
    if (items.length) groups.push(`${label}：${items.map((it) => it.name || it.subject).join('、')}`)
  }
  if (groups.length) lines.push('已整理：' + groups.join('；'))
  if (!lines.length) lines.push(`${act.sub}「${act.text}」已处理。`)
  const text = lines.join('\n')
  store.discussionMessages.push({ role: 'ai', content: text })
  await store.appendPersistedMessage('ai', text, { type: 'config', changes: res.changes || null })
}

async function runChapterCommand(act) {
  if (!act.chapterNo) {
    const t = '未识别章节号，请写成「/章节 第5章 <要点>」'
    store.discussionMessages.push({ role: 'ai', content: t })
    await store.appendPersistedMessage('ai', t)
    return
  }
  if (!activeArticleId.value) {
    const t = '请先在左侧选择一篇或一章，再使用 /章节 生成（章节必须归属某一篇）。'
    store.discussionMessages.push({ role: 'ai', content: t })
    await store.appendPersistedMessage('ai', t)
    return
  }
  const msg = { role: 'ai', content: `（开始生成第${act.chapterNo}章…）\n`, streaming: true }
  store.discussionMessages.push(msg)
  let full = ''
  // 当前所在对话线程（章优先，否则会话）：打包商讨 + 走向建议归位到同一对话框
  const threadChapterId = store.currentChapterId || null
  const threadConversationId = store.currentChapterId ? null : (store.currentConversationId || null)
  try {
    await generateChapterStream(
      store.currentNovelId,
      {
        chapter_no: act.chapterNo,
        prompt_hint: act.hint,
        article_id: activeArticleId.value,
        from_discussion: true,
        thread_chapter_id: threadChapterId,
        thread_conversation_id: threadConversationId,
      },
      (ev, data) => {
        if (ev === 'chunk' && data?.text) {
          full += data.text
          msg.content = full
        } else if (ev === 'done' && data) {
          const wc = data.word_count ? `（${data.word_count} 字）` : ''
          msg.content = full + `\n\n— 已生成并保存第${act.chapterNo}章${wc} —`
        }
      },
    )
  } catch (e) {
    msg.content = (full || '') + '\n[生成失败：' + (e?.message || '未知错误') + ']'
  } finally {
    msg.streaming = false
  }
  await store.appendPersistedMessage('ai', msg.content)
}
const onGenerate = () => {
  if (!store.currentNovelId) return ElMessage.warning('请先选择一本小说')
  if (!activeArticleId.value) return ElMessage.warning('请先在左侧选择一篇或一章，再生成章节')
  genVisible.value = true
}
const onClear = async () => {
  // store.clearDiscussion 内部已区分：未选小说 → 清全局线程；否则清章/会话线程
  await store.clearDiscussion()
  ElMessage.success('已清空')
}
</script>

<style scoped>
.ci {
  background: #fff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px;
}
.ci-quick {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.ci-quick-label { font-size: 12px; color: #909399; }
.ci-chip { cursor: pointer; }
.ci-namegen {
  margin-left: 4px;
  border-style: dashed;
  color: #606266;
}
.ci-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}
.ci-spacer { flex: 1; }
.ci-think {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  user-select: none;
}
.ci-think-label { font-size: 13px; color: #606266; }
.ci-input {
  width: 100%;
}
.ci-input :deep(.el-textarea__inner) {
  min-height: 88px !important;
  padding: 10px 12px;
  font-size: 14px;
  line-height: 1.6;
}
.ci-input :deep(.el-mention-dropdown__list) {
  max-height: 320px;
  overflow-y: auto;
}
</style>
