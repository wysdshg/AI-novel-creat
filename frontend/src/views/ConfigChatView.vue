<template>
  <div class="cc">
    <!-- 工具条 -->
    <div class="cc-toolbar">
      <span class="cc-title">配置对话</span>
      <span class="cc-novel">当前作品：{{ store.currentNovel?.name || '未选择' }}</span>
      <div class="cc-spacer" />
      <el-switch
        v-model="dryRun"
        active-text="仅预览"
        inactive-text="直接写入"
        inline-prompt
        title="开启后 AI 只整理设定、不真正写入资料库"
      />
    </div>

    <!-- 聊天主体 -->
    <el-scrollbar class="cc-body" ref="scrollRef">
      <div v-if="!messages.length" class="cc-empty">
        <el-icon class="cc-empty-icon"><MagicStick /></el-icon>
        <p>用自然语言描述你的设定，AI 会自动整理进资料库。</p>
        <p class="cc-empty-hint">
          例如：「青云门掌门李清尘，门下大弟子楚风，与魔教圣女苏妲己是宿敌。
          门派位于中州，秘境名为焚天谷。」<br />
          也支持显式指令：<code>/角色 李清尘，楚风</code> ·
          <code>/地点 中州，焚天谷</code> ·
          <code>/势力 青云门，魔教</code> ·
          <code>/章节 第5章 楚风初入焚天谷</code>
          （多条指令会按 角色→地点→势力→设定→章节 顺序执行）
        </p>
      </div>

      <div v-for="(m, i) in messages" :key="i" class="cc-msg" :class="m.role">
        <div class="cc-avatar">{{ m.role === 'user' ? '我' : 'AI' }}</div>
        <div class="cc-col">
          <div class="cc-bubble">{{ m.content }}</div>
          <div v-if="m.changes" class="cc-changes">
            <div v-for="grp in changeGroups(m.changes)" :key="grp.key" class="cc-group">
              <div class="cc-group-title">{{ grp.label }}</div>
              <el-tag
                v-for="(item, j) in grp.items"
                :key="j"
                size="small"
                :type="item.action === 'created' ? 'success' : item.action === 'updated' ? 'warning' : 'info'"
                effect="light"
                class="cc-tag"
              >
                {{ item.name || item.subject }}{{ item.object ? ' ↔ ' + item.object : '' }}
                <span class="cc-tag-action">{{ actionText(item.action) }}</span>
                <span v-if="item.reason" class="cc-tag-reason">（{{ item.reason }}）</span>
              </el-tag>
            </div>
            <div v-if="m.dryRun" class="cc-dryhint">⚠ 仅预览，未写入资料库</div>
            <div v-else-if="!hasChanges(m.changes)" class="cc-dryhint">本次没有可写入的设定</div>
          </div>
        </div>
      </div>
    </el-scrollbar>

    <!-- 底部输入 -->
    <div class="cc-input">
      <el-input
        v-model="draft"
        type="textarea"
        :rows="3"
        resize="none"
        placeholder="描述设定，或用 /角色 /地点 /势力 /设定 精确添加，/章节 第X章 生成正文（回车发送，Shift+Enter 换行）"
        @keydown.enter.exact.prevent="send"
      />
      <div class="cc-input-bar">
        <span class="cc-input-tip">可用 /角色 /地点 /势力 /设定 精确添加，/章节 第X章 生成正文；也可直接描述自然语言，AI 会自动抽取</span>
        <el-button type="primary" :icon="Promotion" :loading="sending" @click="send">发送</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Promotion, MagicStick } from '@element-plus/icons-vue'
import { useProjectStore } from '@/store/project'
import { commandApi } from '@/api/database'
import { generateChapterStream } from '@/api/chapter'
import { parseSlashCommands } from '@/utils/slash'

const store = useProjectStore()
const projectId = computed(() => store.currentNovelId)

const messages = ref([])
const draft = ref('')
const sending = ref(false)
const dryRun = ref(false)
const scrollRef = ref(null)

// 配置对话的「聊天记录」本身不入库（落库的是被抽取的设定），但记录文案应随小说留存，
// 否则退出重进后「添加的配置语句」全部消失。按小说分键存 localStorage。
function cfgKey(pid) {
  return 'na_cfg_' + (pid || '')
}
function loadCfgHistory() {
  if (!projectId.value) {
    messages.value = []
    return
  }
  try {
    const raw = localStorage.getItem(cfgKey(projectId.value))
    messages.value = raw ? JSON.parse(raw) : []
  } catch {
    messages.value = []
  }
}
function saveCfgHistory() {
  if (!projectId.value) return
  try {
    localStorage.setItem(cfgKey(projectId.value), JSON.stringify(messages.value))
  } catch (e) {
    console.error('保存配置对话历史失败', e)
  }
}

onMounted(loadCfgHistory)
// 切换小说时切换到对应的配置对话历史
watch(() => store.currentNovelId, loadCfgHistory)
// 任意消息变动（含章节流式生成）都持久化
watch(messages, saveCfgHistory, { deep: true })

const GROUP_LABELS = {
  characters: '角色',
  factions: '势力',
  locations: '地点',
  relations: '关系',
}

function changeGroups(changes) {
  if (!changes) return []
  return Object.keys(GROUP_LABELS)
    .filter((k) => (changes[k] || []).length)
    .map((k) => ({ key: k, label: GROUP_LABELS[k], items: changes[k] }))
}
function hasChanges(changes) {
  return Object.values(changes || {}).some((arr) => (arr || []).length)
}
function actionText(a) {
  return { created: '新建', updated: '更新', skipped: '跳过', preview: '预览' }[a] || a
}

async function send() {
  const text = draft.value.trim()
  if (!text) return
  if (!projectId.value) {
    ElMessage.warning('请先在左侧选择一本小说')
    return
  }
  // 解析显式 /指令（/角色 /地点 /势力 /设定 /章节）。无指令时等价于原行为：
  // 整段作为「设定」类自然语言发送。
  const actions = parseSlashCommands(text)
  messages.value.push({ role: 'user', content: text })
  draft.value = ''
  sending.value = true
  await nextTick()
  scrollToBottom()
  try {
    for (const act of actions) {
      if (act.kind === 'chapter') {
        await runChapter(act)
      } else {
        await runConfig(act)
      }
    }
  } catch (e) {
    messages.value.push({
      role: 'ai',
      content: '调用失败：' + (e?.response?.data?.message || e.message || '未知错误'),
    })
  } finally {
    sending.value = false
    await nextTick()
    scrollToBottom()
  }
}

// 配置类指令（角色/地点/势力/设定/自由文本）→ 调用 config 接口的自然语言抽取
async function runConfig(act) {
  // 单次实体指令透传 entity_type，让后端只抽该类型，不脑补其他实体
  const entityType = (act.sub === '角色' || act.sub === '地点' || act.sub === '势力') ? act.sub : undefined
  const res = await commandApi.run(projectId.value, {
    text: act.prompt || act.text,
    dry_run: dryRun.value,
    entity_type: entityType,
  })
  messages.value.push({
    role: 'ai',
    content: res.reply || '已处理。',
    changes: res.changes,
    model_ok: res.model_ok,
    dryRun: res.dry_run,
  })
}

// /章节 指令 → 流式生成章节正文，实时写入同一条 AI 气泡
async function runChapter(act) {
  if (!act.chapterNo) {
    messages.value.push({
      role: 'ai',
      content: '未识别章节号，请写成「/章节 第5章 <要点>」',
    })
    return
  }
  const msg = { role: 'ai', content: '（开始生成…）\n', streaming: true, chapterNo: act.chapterNo }
  messages.value.push(msg)
  let full = ''
  try {
    await generateChapterStream(
      projectId.value,
      { chapter_no: act.chapterNo, prompt_hint: act.hint },
      (ev, data) => {
        if (ev === 'chunk' && data && data.text) {
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
}

function scrollToBottom() {
  const el = scrollRef.value?.wrapRef
  if (el) el.scrollTop = el.scrollHeight
}
</script>

<style scoped>
.cc { display: flex; flex-direction: column; height: 100%; }
.cc-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 4px 12px;
}
.cc-title { font-weight: 600; font-size: 16px; }
.cc-novel { font-size: 13px; color: #909399; }
.cc-spacer { flex: 1; }
.cc-body { flex: 1; min-height: 0; background: #fff; border: 1px solid var(--el-border-color-light); border-radius: 8px; }
.cc-empty { color: #909399; text-align: center; margin-top: 48px; padding: 0 40px; }
.cc-empty-icon { font-size: 40px; color: #c0c4cc; }
.cc-empty-hint { font-size: 13px; line-height: 1.8; margin-top: 8px; }
.cc-msg {
  display: flex;
  gap: 10px;
  margin-bottom: 18px;
  align-items: flex-start;
  padding: 0 16px;
}
.cc-msg.ai { flex-direction: row; }
.cc-msg.user { flex-direction: row-reverse; }
.cc-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #fff;
}
.cc-msg.user .cc-avatar { background: #409eff; }
.cc-msg.ai .cc-avatar { background: #67c23a; }
.cc-col { display: flex; flex-direction: column; gap: 8px; max-width: 78%; }
.cc-bubble {
  padding: 10px 14px;
  border-radius: 10px;
  background: #f4f4f5;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.cc-msg.user .cc-bubble { background: #ecf5ff; }
.cc-changes {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  background: #fafafa;
  border: 1px dashed var(--el-border-color);
  border-radius: 8px;
}
.cc-group { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.cc-group-title {
  font-size: 12px;
  color: #606266;
  font-weight: 600;
  width: 40px;
  flex-shrink: 0;
}
.cc-tag { margin: 0; }
.cc-tag-action { opacity: 0.7; margin-left: 4px; }
.cc-tag-reason { color: #e6a23c; }
.cc-dryhint { font-size: 12px; color: #e6a23c; }
.cc-input { padding: 12px 0 0; }
.cc-input-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
}
.cc-input-tip { font-size: 12px; color: #909399; }
</style>
