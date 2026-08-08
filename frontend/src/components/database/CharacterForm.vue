<template>
  <el-form :model="form" label-width="80px" class="cf">
    <el-row :gutter="16">
      <el-col :span="12">
        <el-form-item label="姓名" required>
          <el-input v-model="form.name" placeholder="角色姓名" />
        </el-form-item>
      </el-col>
      <el-col :span="12">
        <el-form-item label="地位">
          <el-select v-model="form.role_type" placeholder="选择地位" clearable style="width:100%">
            <el-option label="主角" value="主角" />
            <el-option label="配角" value="配角" />
            <el-option label="反派" value="反派" />
          </el-select>
        </el-form-item>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-form-item label="年龄">
          <el-input-number v-model="form.age" :min="0" :max="999" controls-position="right" style="width:100%" />
        </el-form-item>
      </el-col>
      <el-col :span="12">
        <el-form-item label="性别">
          <el-select v-model="form.gender" placeholder="选择性别" clearable style="width:100%">
            <el-option label="男" value="男" />
            <el-option label="女" value="女" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-form-item label="当前等级">
          <el-input v-model="form.current_level" placeholder="如：筑基初期 / Lv.12" />
        </el-form-item>
      </el-col>
    </el-row>

    <el-form-item label="性格">
      <el-input v-model="form.personality" type="textarea" :rows="2" resize="none" placeholder="性格特征…" />
    </el-form-item>

    <el-form-item label="背景">
      <el-input v-model="form.background" type="textarea" :rows="3" resize="none" placeholder="身世背景…" />
    </el-form-item>

    <el-form-item label="天赋">
      <el-input v-model="form.talent" type="textarea" :rows="2" resize="none" placeholder="天赋/资质…" />
    </el-form-item>

    <el-form-item label="技能">
      <el-select
        v-model="form.skills"
        multiple
        filterable
        allow-create
        default-first-option
        placeholder="输入技能后回车添加，可多个"
        style="width:100%"
      >
        <el-option v-for="s in form.skills" :key="s" :label="s" :value="s" />
      </el-select>
    </el-form-item>

    <el-form-item label="关系网">
      <el-select
        v-model="form.relationship_network"
        multiple
        filterable
        allow-create
        default-first-option
        placeholder="如：与苏晚·恋人（已反目），回车添加多条"
        style="width:100%"
      >
        <el-option v-for="r in form.relationship_network" :key="r" :label="r" :value="r" />
      </el-select>
    </el-form-item>

    <el-form-item label="简介">
      <el-input v-model="form.brief" type="textarea" :rows="3" resize="none" placeholder="一句话简介…" />
    </el-form-item>
  </el-form>
</template>

<script setup>
import { defineModel } from 'vue'

// 表单对象由父组件通过 v-model 传入，直接双向绑定
const form = defineModel({ type: Object, required: true })
</script>

<style scoped>
.cf { padding: 4px 8px 0; }
</style>
