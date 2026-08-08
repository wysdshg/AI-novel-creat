<template>
  <el-card header="新增/编辑角色" shadow="never" class="na-char-form">
    <el-form :model="form" label-width="80px">
      <el-form-item label="姓名"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="外貌"><el-input v-model="form.appearance" type="textarea" :rows="2" /></el-form-item>
      <el-form-item label="性格"><el-input v-model="form.personality" /></el-form-item>
      <el-form-item label="身世"><el-input v-model="form.background" type="textarea" :rows="2" /></el-form-item>
      <el-form-item label="天赋"><el-input v-model="form.talent" /></el-form-item>
      <el-form-item label="当前状态"><el-input v-model="form.status" /></el-form-item>
      <el-form-item label="技能ID"><el-input v-model="skillIds" placeholder="逗号分隔" /></el-form-item>
      <el-form-item label="标签"><el-input v-model="tags" placeholder="逗号分隔" /></el-form-item>
      <el-button type="primary" @click="onSave">保存角色</el-button>
    </el-form>
  </el-card>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { characterApi } from '@/api/database'

// 通过 v-model 接收待编辑对象，emit save 通知父组件刷新列表（解耦，便于后续接入）。
const props = defineProps({ modelValue: { type: Object, default: () => ({}) } })
const emit = defineEmits(['save'])

const form = reactive({ ...props.modelValue })
const skillIds = ref((props.modelValue.skill_ids || []).join(','))
const tags = ref((props.modelValue.tags || []).join(','))

function onSave() {
  const payload = {
    ...form,
    skill_ids: skillIds.value.split(',').filter(Boolean),
    tags: tags.value.split(',').filter(Boolean),
  }
  // TODO: 新建 characterApi.create(projectId, payload) / 编辑 characterApi.update
  console.log('[stub] save character', payload)
  emit('save', payload)
}
</script>

<style scoped>
.na-char-form { margin-bottom: 12px; }
</style>
