<template>
  <el-dialog
    :model-value="modelValue"
    title="新建小说"
    width="480px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
    @open="onOpen"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
      <el-form-item label="小说名称" prop="name">
        <el-input v-model="form.name" maxlength="120" placeholder="如：剑来青云" />
      </el-form-item>

      <el-form-item label="类型">
        <el-select v-model="form.genre" placeholder="选择类型（可选）" clearable style="width: 100%">
          <el-option v-for="g in genres" :key="g" :label="g" :value="g" />
        </el-select>
      </el-form-item>

      <el-form-item label="简介">
        <el-input
          v-model="form.summary"
          type="textarea"
          :rows="4"
          maxlength="2000"
          show-word-limit
          placeholder="一句话概括世界观、主线或卖点（可选）"
        />
      </el-form-item>

      <el-form-item label="状态">
        <el-select v-model="form.status" style="width: 100%">
          <el-option label="草稿" value="draft" />
          <el-option label="写作中" value="writing" />
          <el-option label="暂停" value="paused" />
          <el-option label="已完结" value="finished" />
        </el-select>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="onSubmit">创建</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { projectApi } from '@/api/projects'
import { useProjectStore } from '@/store/project'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'created'])
const store = useProjectStore()

const genres = ['玄幻', '都市', '悬疑', '历史', '科幻', '言情', '武侠', '其他']
const formRef = ref(null)
const submitting = ref(false)

const form = reactive({
  name: '',
  genre: '',
  summary: '',
  status: 'draft',
})

const rules = {
  name: [{ required: true, message: '请输入小说名称', trigger: 'blur' }],
}

const onOpen = () => {
  form.name = ''
  form.genre = ''
  form.summary = ''
  form.status = 'draft'
  formRef.value?.clearValidate?.()
}

const onSubmit = async () => {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    const payload = {
      name: form.name.trim(),
      genre: form.genre || null,
      summary: form.summary.trim() || null,
      status: form.status,
    }
    const novel = await projectApi.create(payload)
    store.addNovel(novel)
    store.selectNovel(novel.id)
    ElMessage.success(`已创建《${novel.name}》`)
    emit('update:modelValue', false)
    emit('created', novel)
  } catch (e) {
    ElMessage.error('创建失败：' + (e?.message || '未知错误'))
  } finally {
    submitting.value = false
  }
}
</script>
