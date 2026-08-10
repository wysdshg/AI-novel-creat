<template>
  <el-dialog
    :model-value="modelValue"
    title="生成章节"
    width="760px"
    top="5vh"
    :close-on-click-modal="!generating"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <div class="gcd-desc">
      填写本章的结构化要素，将作为生成约束拼入模型 Prompt。字段越具体，AI 越不易跑偏。
    </div>

    <template v-if="!generating && !result">
      <el-alert
        v-if="!effectiveArticleId"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        title="尚未选择所属篇"
        description="请先在左侧树中选择一篇或一章，再生成章节（章节必须归属于某一篇）。"
      />
      <el-form label-position="top" class="gcd-form">
        <el-form-item label="章节标题">
          <el-input v-model="title" placeholder="例如：第七章 · 宗门大比" />
        </el-form-item>
        <el-form-item label="章节序号">
          <el-input-number v-model="chapterNo" :min="1" />
          <span class="gcd-hint">默认接续当前小说已有章节数 +1。</span>
        </el-form-item>

        <el-divider content-position="left">本章要素</el-divider>

        <ChapterElementsForm ref="formRef" />

        <el-form-item label="附加要求">
          <el-input
            v-model="extra"
            type="textarea"
            :rows="3"
            placeholder="温度 / 字数 / 特殊风格等补充说明（可选）"
            resize="none"
          />
        </el-form-item>
      </el-form>
    </template>

    <template v-else>
      <div class="gcd-status">
        <el-icon v-if="generating" class="is-loading"><Loading /></el-icon>
        <el-tag :type="generating ? 'warning' : (result ? 'success' : 'info')">
          {{ generating ? '生成中…' : (result ? `已生成（${wordCount} 字）` : '未开始') }}
        </el-tag>
        <el-tag v-if="ctx" size="small" type="info" effect="plain">
          上下文 {{ ctx.total_chars }} 字 · 占预算 {{ ctx.budget?.usage_pct ?? 0 }}%
        </el-tag>
        <el-tag v-if="ingestState" size="small" :type="ingestState.type" effect="plain">
          {{ ingestState.text }}
        </el-tag>
      </div>

      <!-- 这次 AI 到底读了什么：人设崩了能直接看出是没读到还是读了没听 -->
      <el-collapse v-if="ctx" class="gcd-ctx">
        <el-collapse-item name="ctx">
          <template #title>
            <span class="gcd-ctx-title">
              本次读取：{{ (ctx.budget?.kept || []).length }} 个上下文块
              <template v-if="(ctx.references || []).length">
                · {{ ctx.references.length }} 份参考资料
              </template>
              <template v-if="(ctx.skills?.active || []).length">
                · {{ ctx.skills.active.length }} 条 SKILL
              </template>
            </span>
          </template>
          <div class="gcd-ctx-body">
            <div class="gcd-ctx-row">
              <b>上下文块</b>
              <el-tag
                v-for="k in (ctx.budget?.kept || [])"
                :key="k.key"
                size="small"
                effect="plain"
              >{{ blockLabel(k.key) }} {{ k.chars }}字</el-tag>
            </div>
            <div v-if="(ctx.budget?.dropped || []).length" class="gcd-ctx-row">
              <b>因预算丢弃</b>
              <el-tag
                v-for="d in ctx.budget.dropped"
                :key="d.key"
                size="small"
                type="danger"
                effect="plain"
              >{{ blockLabel(d.key) }}</el-tag>
            </div>
            <div v-if="(ctx.references || []).length" class="gcd-ctx-row">
              <b>参考资料</b>
              <span class="gcd-ctx-text">
                {{ ctx.references.map((r) => r.filename).join('、') }}
              </span>
            </div>
            <div v-if="(ctx.skills?.active || []).length" class="gcd-ctx-row">
              <b>生效 SKILL</b>
              <el-tag
                v-for="s in ctx.skills.active"
                :key="s.name"
                size="small"
                type="success"
                effect="plain"
              >{{ s.name }}</el-tag>
            </div>
            <div v-if="(ctx.skills?.suppressed || []).length" class="gcd-ctx-row">
              <b>被同类挤掉</b>
              <el-tag
                v-for="s in ctx.skills.suppressed"
                :key="s.id || s.name"
                size="small"
                type="info"
                effect="plain"
              >{{ s.name }}（{{ s.reason }}）</el-tag>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>

      <!-- AI 味检测报告 -->
      <div v-if="scanReport" class="gcd-scan" :class="scanLevelClass">
        <div class="gcd-scan-head">
          <span class="gcd-scan-score">{{ scanReport.score }}</span>
          <span class="gcd-scan-grade">{{ scanReport.grade }}</span>
          <span class="gcd-scan-meta">
            {{ scanReport.issue_count }} 处可疑 · 每千字 {{ scanReport.per_thousand }} 处
          </span>
          <div class="gcd-spacer" />
          <el-button size="small" text @click="showIssues = !showIssues">
            {{ showIssues ? '收起' : '查看明细' }}
          </el-button>
        </div>
        <div v-if="showIssues" class="gcd-scan-list">
          <div v-for="(is, i) in (scanReport.issues || []).slice(0, 40)" :key="i" class="gcd-issue">
            <el-tag size="small" :type="sevType(is.severity)" effect="plain">
              {{ is.category || is.type }}
            </el-tag>
            <code class="gcd-issue-hit">{{ is.matched }}</code>
            <span class="gcd-issue-ctx">{{ is.context }}</span>
            <span v-if="is.advice" class="gcd-issue-fix">→ {{ is.advice }}</span>
          </div>
          <div v-if="(scanReport.issues || []).length > 40" class="gcd-issue-more">
            还有 {{ scanReport.issues.length - 40 }} 处未展示
          </div>
        </div>
      </div>

      <el-input
        :model-value="streamText"
        type="textarea"
        :rows="scanReport ? 12 : 18"
        readonly
        resize="none"
        class="gcd-result"
        placeholder="生成结果将在此实时显示"
      />
    </template>

    <template #footer>
      <el-button
        v-if="generating"
        type="danger"
        plain
        :loading="true"
      >生成中…</el-button>
      <template v-else>
        <el-button @click="emit('update:modelValue', false)">
          {{ result ? '关闭' : '取消' }}
        </el-button>
        <el-button v-if="!result" type="primary" :disabled="!effectiveArticleId" @click="onGenerate">生成章节</el-button>
        <el-button v-else type="primary" :disabled="!effectiveArticleId" @click="onGenerate">重新生成</el-button>
        <el-button v-if="result" @click="copyResult">复制正文</el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import ChapterElementsForm from './ChapterElementsForm.vue'
import { generateChapterStream } from '@/api/chapter'
import { useProjectStore } from '@/store/project'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  projectId: { type: String, default: '' },
  articleId: { type: String, default: '' },
  enableThinking: { type: Boolean, default: true },
})
const emit = defineEmits(['update:modelValue'])

const store = useProjectStore()

// 有效的篇上下文：优先来自父组件传入的 articleId，其次当前选中的篇/章。
// 为空时禁止生成（后端也会 400 兜底），避免产出「孤儿章」（不挂在任何篇下、侧栏不显示）。
const effectiveArticleId = computed(() => {
  if (props.articleId) return props.articleId
  if (store.currentArticle?.id) return store.currentArticle.id
  if (store.currentChapter?.article_id) return store.currentChapter.article_id
  return ''
})

const title = ref('')
const chapterNo = ref(1)
const extra = ref('')
const formRef = ref(null)

const generating = ref(false)
const streamText = ref('')
const result = ref(false)
const wordCount = ref(0)

// 生成过程中后端回传的三类元信息
const ctx = ref(null)             // context 事件：这次读了哪些资料
const scanReport = ref(null)      // validate 事件：AI 味检测报告
const ingestState = ref(null)     // ingest 事件：记忆抽取 / 走向推送结果
const showIssues = ref(false)

const BLOCK_LABELS = {
  task: '本章任务',
  discussion: '商讨记录',
  world: '世界观',
  characters: '角色卡',
  entities: '势力地点',
  foreshadows: '伏笔',
  stage_memory: '阶段脉络',
  recent_memory: '最近章回顾',
  prev_tail: '上一章结尾',
  references: '参考资料',
}
const blockLabel = (k) => BLOCK_LABELS[k] || k

const scanLevelClass = computed(() => {
  const s = scanReport.value?.score ?? 100
  if (s >= 80) return 'is-good'
  if (s >= 55) return 'is-warn'
  return 'is-bad'
})
const sevType = (s) => (s >= 3 ? 'danger' : s === 2 ? 'warning' : 'info')

// 打开时根据当前小说章节数预设序号
if (store.currentNovel?.chapterCount) {
  chapterNo.value = store.currentNovel.chapterCount + 1
}

// 关键修复：每次弹窗被（重新）打开时，复位全部生成状态，
// 否则上一次的 result=true 会残留，导致再次打开仍停在「生成结束」页、没有生成按钮。
// 组件常驻挂载（仅 el-dialog 显隐），关闭后 ref 不会销毁，必须手动复位。
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      generating.value = false
      result.value = false
      streamText.value = ''
      wordCount.value = 0
      ctx.value = null
      scanReport.value = null
      ingestState.value = null
      showIssues.value = false
      title.value = ''
      extra.value = ''
      if (store.currentNovel?.chapterCount) {
        chapterNo.value = store.currentNovel.chapterCount + 1
      }
    }
  },
)

const onGenerate = async () => {
  const projectId = props.projectId || store.currentNovelId
  if (!projectId) return ElMessage.warning('请先选择一本小说')
  if (!effectiveArticleId.value) return ElMessage.warning('请先在左侧选择一篇或一章，再生成章节')
  const elements = formRef.value?.getElements?.() ?? []
  const filled = elements.filter((e) => e.value && e.value.trim())
  const hintParts = filled.map((e) => `${e.label}：${e.value}`)
  if (extra.value.trim()) hintParts.push(extra.value.trim())
  const prompt_hint = [title.value ? `标题：${title.value}` : '', ...hintParts].filter(Boolean).join('\n')

  generating.value = true
  streamText.value = ''
  result.value = false
  wordCount.value = 0
  ctx.value = null
  scanReport.value = null
  ingestState.value = null
  showIssues.value = false

  const body = {
    chapter_no: chapterNo.value,
    prompt_hint,
    from_discussion: false,
    trigger_foreshadow_ids: [],
    word_range: { min: 3000, max: 5000 },
    temperature: 0.4,
    enable_thinking: props.enableThinking,
    article_id: effectiveArticleId.value || null,
  }

  try {
    await generateChapterStream(projectId, body, (event, data) => {
      if (event === 'chunk') {
        streamText.value += data.text || ''
      } else if (event === 'context') {
        ctx.value = data
      } else if (event === 'validate') {
        scanReport.value = data && data.score !== undefined ? data : null
      } else if (event === 'ingest_start') {
        ingestState.value = { type: 'warning', text: '正在抽取本章记忆…' }
      } else if (event === 'ingest') {
        if (data.error) {
          ingestState.value = { type: 'danger', text: '记忆抽取失败' }
        } else {
          const bits = []
          if (data.memory_id) bits.push('记忆已存')
          if (data.directions_pushed) bits.push(`${data.directions_pushed} 条走向已推送`)
          if ((data.new_entities || []).length) bits.push(`${data.new_entities.length} 个新实体待确认`)
          if (data.stage_compressed) bits.push('阶段摘要已压缩')
          ingestState.value = {
            type: data.fallback ? 'warning' : 'success',
            text: (data.fallback ? '兜底抽取：' : '') + (bits.join(' · ') || '已处理'),
          }
        }
      } else if (event === 'done') {
        wordCount.value = data.word_count || streamText.value.length
      }
    })
    result.value = true
    // 4 级结构：生成后刷新侧栏树，让新章出现在对应篇下
    try {
      await store.loadStructure(projectId)
    } catch {
      /* 刷新失败不影响已生成结果 */
    }
    ElMessage.success('章节生成完成')
  } catch (e) {
    ElMessage.error('生成失败：' + (e?.message || e))
  } finally {
    generating.value = false
  }
}

const copyResult = async () => {
  try {
    await navigator.clipboard.writeText(streamText.value)
    ElMessage.success('已复制正文')
  } catch {
    ElMessage.warning('复制失败，请手动选择文本复制')
  }
}
</script>

<style scoped>
.gcd-desc {
  font-size: 13px;
  color: #909399;
  margin-bottom: 12px;
}
.gcd-form { max-height: 62vh; overflow-y: auto; padding-right: 4px; }
.gcd-hint { font-size: 12px; color: #909399; margin-left: 10px; }
.gcd-status { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.gcd-result :deep(.el-textarea__inner) {
  font-size: 14px;
  line-height: 1.7;
  background: #fafafa;
}
.gcd-spacer { flex: 1; }

/* —— 上下文透明化面板 —— */
.gcd-ctx { margin-bottom: 10px; border-top: none; }
.gcd-ctx :deep(.el-collapse-item__header) { height: 34px; line-height: 34px; font-size: 12px; }
.gcd-ctx-title { color: #606266; font-size: 12px; }
.gcd-ctx-body { display: flex; flex-direction: column; gap: 8px; }
.gcd-ctx-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 12px;
}
.gcd-ctx-row b { color: #909399; font-weight: 500; min-width: 68px; }
.gcd-ctx-text { color: #606266; }

/* —— AI 味检测面板 —— */
.gcd-scan {
  border: 1px solid var(--el-border-color-light);
  border-left-width: 3px;
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 10px;
  background: #fafafa;
}
.gcd-scan.is-good { border-left-color: #67c23a; }
.gcd-scan.is-warn { border-left-color: #e6a23c; }
.gcd-scan.is-bad { border-left-color: #f56c6c; }
.gcd-scan-head { display: flex; align-items: center; gap: 10px; }
.gcd-scan-score { font-size: 20px; font-weight: 700; color: #303133; }
.gcd-scan-grade { font-size: 13px; font-weight: 600; color: #606266; }
.gcd-scan-meta { font-size: 12px; color: #909399; }
.gcd-scan-list {
  margin-top: 8px;
  max-height: 220px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.gcd-issue {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
  flex-wrap: wrap;
  padding-bottom: 5px;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.gcd-issue-hit {
  background: #fff0f0;
  color: #d94545;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: inherit;
}
.gcd-issue-ctx { color: #909399; flex: 1; min-width: 200px; }
.gcd-issue-fix { color: #67c23a; }
.gcd-issue-more { font-size: 12px; color: #909399; text-align: center; }
</style>
