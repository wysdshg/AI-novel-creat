<template>
  <div class="stub">
    <h2 class="stub-title">线索 / 伏笔</h2>
    <el-alert type="info" :closable="false" show-icon title="伏笔线索全生命周期管理">
      <p>埋下 → 启用回收，状态追踪。章节生成前置检索可触发伏笔，前端提供伏笔时间轴可视化。</p>
    </el-alert>
    <el-empty description="暂无伏笔（功能待实现）" class="stub-empty" />
    <el-card class="stub-note" shadow="never">
      <p>后端接口（待实现）：<code>GET /api/v1/projects/{id}/foreshadows</code></p>
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
