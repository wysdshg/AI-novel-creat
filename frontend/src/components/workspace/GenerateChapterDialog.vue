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
      </div>
      <el-input
        :model-value="streamText"
        type="textarea"
        :rows="18"
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
        <el-button v-if="!result" type="primary" @click="onGenerate">生成章节</el-button>
        <el-button v-else type="primary" @click="copyResult">复制正文</el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import ChapterElementsForm from './ChapterElementsForm.vue'
import { generateChapterStream } from '@/api/chapter'
import { useProjectStore } from '@/store/project'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  projectId: { type: String, default: '' },
  enableThinking: { type: Boolean, default: true },
})
const emit = defineEmits(['update:modelValue'])

const store = useProjectStore()

const title = ref('')
const chapterNo = ref(1)
const extra = ref('')
const formRef = ref(null)

const generating = ref(false)
const streamText = ref('')
const result = ref(false)
const wordCount = ref(0)

// 打开时根据当前小说章节数预设序号
if (store.currentNovel?.chapterCount) {
  chapterNo.value = store.currentNovel.chapterCount + 1
}

const onGenerate = async () => {
  const projectId = props.projectId || store.currentNovelId
  if (!projectId) return ElMessage.warning('请先选择一本小说')
  const elements = formRef.value?.getElements?.() ?? []
  const filled = elements.filter((e) => e.value && e.value.trim())
  const hintParts = filled.map((e) => `${e.label}：${e.value}`)
  if (extra.value.trim()) hintParts.push(extra.value.trim())
  const prompt_hint = [title.value ? `标题：${title.value}` : '', ...hintParts].filter(Boolean).join('\n')

  generating.value = true
  streamText.value = ''
  result.value = false
  wordCount.value = 0

  const body = {
    chapter_no: chapterNo.value,
    prompt_hint,
    from_discussion: false,
    trigger_foreshadow_ids: [],
    word_range: { min: 3000, max: 5000 },
    temperature: 0.4,
    enable_thinking: props.enableThinking,
  }

  try {
    await generateChapterStream(projectId, body, (event, data) => {
      if (event === 'chunk') {
        streamText.value += data.text || ''
      } else if (event === 'done') {
        wordCount.value = data.word_count || streamText.value.length
      }
    })
    result.value = true
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
</style>
