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
          门派位于中州，秘境名为焚天谷。」
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
        placeholder="描述设定，回车发送（Shift+Enter 换行）"
        @keydown.enter.exact.prevent="send"
      />
      <div class="cc-input-bar">
        <span class="cc-input-tip">AI 会自动抽取角色 / 势力 / 地点 / 关系并写入对应资料库</span>
        <el-button type="primary" :icon="Promotion" :loading="sending" @click="send">发送</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Promotion, MagicStick } from '@element-plus/icons-vue'
import { useProjectStore } from '@/store/project'
import { commandApi } from '@/api/database'

const store = useProjectStore()
const projectId = computed(() => store.currentNovelId)

const messages = ref([])
const draft = ref('')
const sending = ref(false)
const dryRun = ref(false)
const scrollRef = ref(null)

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
  messages.value.push({ role: 'user', content: text })
  draft.value = ''
  sending.value = true
  await nextTick()
  scrollToBottom()
  try {
    const res = await commandApi.run(projectId.value, { text, dry_run: dryRun.value })
    messages.value.push({
      role: 'ai',
      content: res.reply || '已处理。',
      changes: res.changes,
      model_ok: res.model_ok,
      dryRun: res.dry_run,
    })
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
