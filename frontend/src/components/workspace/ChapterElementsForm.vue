<template>
  <div class="cef">
    <div v-for="item in items" :key="item.key" class="cef-item">
      <div class="cef-item-head">
        <span class="cef-item-label">{{ item.label }}</span>
        <el-button
          v-if="item.ai"
          size="small"
          text
          type="primary"
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
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

// 本章要素：生成章节时作为结构化约束拼入 Prompt。
// 字段顺序与截图一致：角色 / 背景 / 故事发展 / 最终结果 / 冲突。
// 该组件被右侧常驻面板与「生成章节」弹窗共用，保证格式统一、可维护。
const items = ref([
  { key: 'role', label: '角色', value: '', placeholder: '本场出场角色…', rows: 3 },
  { key: 'background', label: '背景', value: '', placeholder: '本章背景设定…', rows: 4, ai: true, aiText: 'AI 生成' },
  { key: 'development', label: '故事发展', value: '', placeholder: '剧情推进方向…', rows: 4, ai: true, aiText: 'AI 润色' },
  { key: 'result', label: '最终结果', value: '', placeholder: '本章结局…', rows: 3 },
  { key: 'conflict', label: '冲突', value: '', placeholder: '核心冲突…', rows: 3 },
])

const onAi = (item) => ElMessage.info(`「${item.label}」${item.aiText}（功能待实现，将调用设定/创作模型）`)

// 暴露给父组件，便于提交时读取
defineExpose({
  getElements: () => items.value.map((i) => ({ key: i.key, label: i.label, value: i.value })),
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
</style>
