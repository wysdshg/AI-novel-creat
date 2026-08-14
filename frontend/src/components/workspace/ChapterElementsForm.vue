<template>
  <div class="cef">
    <div
      v-for="item in items"
      :key="item.key"
      class="cef-item"
      :class="{ 'cef-required': item.required }"
    >
      <div class="cef-item-head">
        <span class="cef-item-label">
          {{ item.label }}
          <span v-if="item.required" class="cef-required-mark">*</span>
        </span>
        <el-button
          v-if="item.ai"
          size="small"
          text
          type="primary"
          :loading="item.loading"
          @click="onAi(item)"
        >{{ item.aiText }}</el-button>
      </div>
      <el-input
        v-model="item.value"
        type="textarea"
        :rows="item.rows || 3"
        :placeholder="item.placeholder"
        resize="none"
      />
      <div v-if="item.error" class="cef-item-error">{{ item.error }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/store/project'
import { assistApi } from '@/api/assist'

const store = useProjectStore()

// 同一组件内 AI 按钮全局冷却：避免连点触发厂商 429 限流
const COOLDOWN_MS = 6000
let lastAiAt = 0

// 本章要素：生成章节时作为结构化约束拼入 Prompt。
// 字段顺序即向模型陈述的顺序，按小说创作流程排列。
const items = ref([
  {
    key: 'scene_goal',
    label: '场景目标',
    value: '',
    placeholder: '本章要达成的叙事目标：主角要做什么、解决什么问题、拿到什么信息？（必填）',
    rows: 2,
    required: true,
  },
  {
    key: 'characters',
    label: '出场角色',
    value: '',
    placeholder: '本章出场的关键角色（可写名字 + 本场立场/目标）',
    rows: 2,
  },
  {
    key: 'background',
    label: '时空背景',
    value: '',
    placeholder: '本章发生的时间、地点、环境氛围…',
    rows: 3,
    ai: true,
    aiText: 'AI 生成',
    loading: false,
  },
  {
    key: 'conflict',
    label: '核心冲突',
    value: '',
    placeholder: '本章的主要矛盾：人与环境 / 人与人 / 人与自我',
    rows: 3,
  },
  {
    key: 'beats',
    label: '情节节拍',
    value: '',
    placeholder: '用 3~5 句话概括本章推进：起→承→转→合',
    rows: 4,
    ai: true,
    aiText: 'AI 润色',
    loading: false,
  },
  {
    key: 'hook',
    label: '结尾钩子',
    value: '',
    placeholder: '本章结尾留下的悬念/转折/下一章必须接住的东西',
    rows: 2,
  },
  {
    key: 'style',
    label: '风格约束',
    value: '',
    placeholder: '本章的语气、节奏、视角、特殊要求（如：快节奏、压抑、轻松、白描）',
    rows: 2,
  },
])

function validate() {
  let ok = true
  for (const item of items.value) {
    item.error = ''
    if (item.required && !item.value.trim()) {
      item.error = `「${item.label}」为必填项`
      ok = false
    }
  }
  return ok
}

function clearErrors() {
  for (const item of items.value) {
    item.error = ''
  }
}

function reset() {
  for (const item of items.value) {
    item.value = ''
    item.error = ''
    item.loading = false
  }
}

const onAi = async (item) => {
  const projectId = store.currentNovelId
  if (!projectId) {
    ElMessage.warning('请先选择一本小说')
    return
  }
  const now = Date.now()
  const remain = COOLDOWN_MS - (now - lastAiAt)
  if (lastAiAt && remain > 0) {
    ElMessage.warning(`AI 调用过于频繁，请等待 ${Math.ceil(remain / 1000)} 秒后再试`)
    return
  }
  // 收集本章其他已填要素，作为一致性上下文（排除当前字段自身）
  const context = {}
  for (const it of items.value) {
    if (it.key !== item.key && it.value && it.value.trim()) {
      context[it.key] = it.value.trim()
    }
  }
  item.loading = true
  lastAiAt = Date.now()
  try {
    // 注意：http.js 拦截器已经把外层 {code, data} 解包，返回的是内层 data
    const data = await assistApi.polishElement(projectId, {
      field_label: item.label,
      current_text: item.value || '',
      mode: item.value && item.value.trim() ? 'polish' : 'generate',
      context,
      model_id: store.currentModelId || undefined,
    })
    const text = data?.text
    if (!text) {
      ElMessage.warning('模型返回为空，请重试')
      return
    }
    item.value = text
    ElMessage.success(`「${item.label}」已${data?.mode === 'generate' ? '生成' : '润色'}`)
  } catch (e) {
    // 统一拦截器已对非零 code / 网络错误弹 toast，这里仅兜底静默处理，避免重复提示
    console.error('polishElement 失败：', e)
  } finally {
    item.loading = false
  }
}

// 暴露给父组件，便于提交时读取
defineExpose({
  getElements: () => items.value.map((i) => ({ key: i.key, label: i.label, value: i.value })),
  validate,
  clearErrors,
  reset,
})
</script>

<style scoped>
.cef-item { margin-bottom: 14px; }
.cef-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.cef-item-label { font-size: 13px; color: #606266; font-weight: 500; }
.cef-required-mark { color: #f56c6c; margin-left: 2px; }
.cef-item-error { color: #f56c6c; font-size: 12px; margin-top: 4px; }
</style>
