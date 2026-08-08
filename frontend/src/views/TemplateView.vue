<template>
  <div class="stub">
    <h2 class="stub-title">套路模板</h2>
    <el-alert type="info" :closable="false" show-icon title="网文高频模板组件化">
      <p>秘境夺宝 / 宗门大比 / 穿越重生 / 复仇逆袭等。选择模板后配置角色与冲突，AI 自动拆分大纲。</p>
    </el-alert>
    <el-row :gutter="16" class="stub-grid">
      <el-col :span="6" v-for="t in templates" :key="t">
        <el-card shadow="hover" class="stub-card">{{ t }}</el-card>
      </el-col>
    </el-row>
    <el-card class="stub-note" shadow="never">
      <p>后端接口（待实现）：<code>POST /api/v1/projects/{id}/templates/generate-outline</code></p>
    </el-card>
  </div>
</template>

<script setup>
const templates = ['秘境夺宝', '宗门大比', '穿越重生', '复仇逆袭', '悬疑探案', '团战突围', '都市奇遇']
</script>

<style scoped>
.stub-title { margin: 0 0 16px; }
.stub-grid { margin-top: 16px; }
.stub-card { text-align: center; cursor: pointer; }
.stub-note { margin-top: 16px; }
.stub-note code { background: #f4f4f5; padding: 2px 6px; border-radius: 4px; }
</style>
