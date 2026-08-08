<template>
  <div>
    <el-card shadow="never" class="na-tip">
      <b>模块2/3 · 章节生成控制器（需求 2、3）</b>
      <span class="na-stub-tip"> 单章生成、字数 3000~5000、三层防发散；整合商讨缓存+资料库+伏笔。</span>
    </el-card>

    <el-row :gutter="16">
      <el-col :span="10">
        <el-card header="生成配置" shadow="never">
          <el-form :model="genForm" label-width="90px">
            <el-form-item label="章节号"><el-input-number v-model="genForm.chapter_no" :min="1" /></el-form-item>
            <el-form-item label="剧情提示"><el-input v-model="genForm.prompt_hint" type="textarea" :rows="3" /></el-form-item>
            <el-form-item label="温度">
              <el-slider v-model="genForm.temperature" :min="0" :max="1" :step="0.1" />
            </el-form-item>
            <el-button type="primary" :loading="generating" @click="onGenerate">开始创作本章</el-button>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="14">
        <el-card header="正文预览" shadow="never">
          <div class="na-preview">{{ previewText || '（生成结果将在此流式展示，脚手架占位）' }}</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { generateChapterStream } from '@/api/chapter'

const generating = ref(false)
const previewText = ref('')
const genForm = reactive({
  chapter_no: 1,
  prompt_hint: '',
  from_discussion: true,
  trigger_foreshadow_ids: [],
  word_range: { min: 3000, max: 5000 },
  temperature: 0.4,
})

// TODO: 接入 SSE。generateChapterStream 已封装事件回调（start/chunk/validate/done）。
async function onGenerate() {
  generating.value = true
  previewText.value = ''
  try {
    // await generateChapterStream(projectId, genForm, (event, data) => { ... })
  } finally {
    generating.value = false
  }
}
</script>

<style scoped>
.na-tip { margin-bottom: 12px; }
.na-preview { min-height: 320px; white-space: pre-wrap; line-height: 1.8; color: #303133; }
</style>
