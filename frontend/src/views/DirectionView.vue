<template>
  <div class="stub">
    <h2 class="stub-title">走向推荐</h2>
    <el-alert type="info" :closable="false" show-icon title="单章生成后的差异化后续走向推演">
      <p>读取章节结尾、人物状态、未触发伏笔，输出 3~5 条后续走向，可一键加入下一轮商讨。</p>
    </el-alert>
    <el-empty description="暂无推荐走向（功能待实现）" class="stub-empty" />
    <el-card class="stub-note" shadow="never">
      <p>后端接口（待实现）：<code>POST /api/v1/projects/{id}/chapters/{n}/directions</code></p>
    </el-card>
  </div>
</template>

<script setup></script>

<style scoped>
.stub-title { margin: 0 0 16px; }
.stub-empty { padding: 24px 0; }
.stub-note { margin-top: 16px; }
.stub-note code { background: #f4f4f5; padding: 2px 6px; border-radius: 4px; }
</style>
