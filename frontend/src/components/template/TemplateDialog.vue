<template>
  <el-dialog
    :model-value="modelValue"
    title="套路模板配置"
    width="520px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-steps :active="step" finish-status="success" class="na-steps">
      <el-step title="选择模板" />
      <el-step title="配置冲突" />
      <el-step title="生成大纲" />
    </el-steps>

    <div v-if="step === 0">
      <el-radio-group v-model="selected">
        <el-radio-button v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}</el-radio-button>
      </el-radio-group>
    </div>

    <div v-else-if="step === 1">
      <el-form :model="cfg" label-width="90px">
        <el-form-item label="参与角色"><el-input v-model="cfg.participants" placeholder="角色ID，逗号分隔" /></el-form-item>
        <el-form-item label="对立势力"><el-input v-model="cfg.opponent_faction" /></el-form-item>
        <el-form-item label="核心矛盾"><el-input v-model="cfg.core_conflict" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="背景来源">
          <el-radio-group v-model="cfg.background_source">
            <el-radio value="manual">手动填写</el-radio>
            <el-radio value="ai_auto">AI 结合摘要生成</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="预估章数"><el-input-number v-model="cfg.est_chapters" :min="1" /></el-form-item>
      </el-form>
    </div>

    <div v-else>
      <p class="na-stub-tip">TODO: 调用 templateApi.generateOutline → 展示 AI 拆分的大纲（每章核心/出场/伏笔位），支持增删改。</p>
    </div>

    <template #footer>
      <el-button v-if="step > 0" @click="step--">上一步</el-button>
      <el-button type="primary" @click="next">{{ step === 2 ? '完成' : '下一步' }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { templateApi } from '@/api/template'

defineProps({
  modelValue: Boolean,
  templates: { type: Array, default: () => [] },
})
defineEmits(['update:modelValue'])

const step = ref(0)
const selected = ref('')
const cfg = reactive({
  participants: '', opponent_faction: '', core_conflict: '',
  background_source: 'manual', est_chapters: 30,
})

function next() {
  if (step.value < 2) {
    step.value++
    return
  }
  // TODO: templateApi.generateOutline(projectId, selected.value, {...cfg})
  console.log('[stub] generate outline', selected.value, cfg)
  step.value = 0
}
</script>

<style scoped>
.na-steps { margin-bottom: 16px; }
</style>
