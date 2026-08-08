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
    </div>

    <el-mention
      ref="mentionsRef"
      v-model="text"
      class="ci-input"
      :options="sortedMentionOptions"
      :prefix="['@']"
      :rows="4"
      resize="none"
      placeholder="输入对话，讨论本章内容；点击「生成章节」打包本对话与本章要素并生成小说"
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
      <el-button type="primary" @click="onGenerate">生成章节</el-button>
    </div>

    <GenerateChapterDialog v-model="genVisible" :project-id="store.currentNovelId" :enable-thinking="enableThinking" />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/store/project'
import { characterApi, factionApi } from '@/api/database'
import GenerateChapterDialog from './GenerateChapterDialog.vue'

const store = useProjectStore()
const text = ref('')
const genVisible = ref(false)
const mentionsRef = ref(null)
const characters = ref([])
const factions = ref([])
// 思考开关：默认关闭（回复更快、更省 token）；开启后会在回复下方展示模型推理过程。
// 注意：聊天与「生成章节」共用此开关，但 Ollama 原生适配器始终返回干净正文，
// 因此章节正文不受其影响（仅在聊天界面决定是否展示思考过程）。
const enableThinking = ref(false)
// 当前会话中最近被 @ 的条目 ID（按时间先后放入；越后放表示越近使用）
const recentlyMentionedIds = ref([])

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
  if (!store.currentNovelId) return ElMessage.warning('请先选择一本小说')
  if (store.sendingDiscussion) return
  text.value = ''
  await store.sendDiscussion(content, enableThinking.value)
}
const onGenerate = () => {
  if (!store.currentNovelId) return ElMessage.warning('请先选择一本小说')
  genVisible.value = true
}
const onClear = async () => {
  if (!store.currentNovelId) return
  await store.clearDiscussion()
  ElMessage.success('已清空商讨记录')
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
