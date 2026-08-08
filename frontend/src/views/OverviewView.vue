<template>
  <div class="stub">
    <h2 class="stub-title">概览</h2>
    <el-row :gutter="16">
      <el-col :span="8" v-for="c in cards" :key="c.title">
        <el-card shadow="hover">
          <div class="stub-card-title">{{ c.title }}</div>
          <div class="stub-card-val">{{ c.val }}</div>
          <div class="stub-card-desc">{{ c.desc }}</div>
        </el-card>
      </el-col>
    </el-row>
    <el-card class="stub-note" shadow="never">
      <template #header>说明</template>
      <p>概览汇总当前作品的进度、近期记忆摘要、已启用伏笔统计等。</p>
      <p>后端接口（待实现）：<code>GET /api/v1/projects/{id}/summary</code></p>
    </el-card>
  </div>
</template>

<script setup>
const cards = [
  { title: '章节数', val: '0', desc: '已生成章节' },
  { title: '角色数', val: '0', desc: '资料库角色' },
  { title: '活跃伏笔', val: '0', desc: '已埋未回收' },
]
</script>

<style scoped>
.stub-title { margin: 0 0 16px; }
.stub-card-title { color: #909399; font-size: 13px; }
.stub-card-val { font-size: 28px; font-weight: 600; margin: 8px 0; }
.stub-card-desc { color: #909399; font-size: 12px; }
.stub-note { margin-top: 16px; }
.stub-note code { background: #f4f4f5; padding: 2px 6px; border-radius: 4px; }
</style>
