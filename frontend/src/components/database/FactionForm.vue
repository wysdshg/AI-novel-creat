<template>
  <el-form :model="form" label-width="80px" class="ff">
    <el-row :gutter="16">
      <el-col :span="12">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="势力名称" />
        </el-form-item>
      </el-col>
      <el-col :span="12">
        <el-form-item label="状态">
          <el-select v-model="form.status" placeholder="选择状态" clearable style="width:100%">
            <el-option label="活跃" value="active" />
            <el-option label="蛰伏" value="dormant" />
            <el-option label="覆灭" value="fallen" />
          </el-select>
        </el-form-item>
      </el-col>
    </el-row>

    <el-form-item label="描述">
      <el-input v-model="form.description" type="textarea" :rows="4" resize="none" placeholder="势力背景、目标、风格…" />
    </el-form-item>

    <el-form-item label="核心成员">
      <el-select
        v-model="form.members"
        multiple
        filterable
        allow-create
        default-first-option
        placeholder="输入角色ID或名称后回车添加"
        style="width:100%"
      >
        <el-option v-for="m in form.members" :key="m" :label="m" :value="m" />
      </el-select>
    </el-form-item>
  </el-form>
</template>

<script setup>
import { defineModel } from 'vue'

const form = defineModel({ type: Object, required: true })
</script>

<style scoped>
.ff { padding: 4px 8px 0; }
</style>
