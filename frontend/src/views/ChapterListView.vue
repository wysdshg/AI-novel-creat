<template>
  <div class="stub">
    <h2 class="stub-title">章节列表</h2>
    <el-table :data="[]" empty-text="暂无章节（功能待实现）" border>
      <el-table-column type="index" label="#" width="60" />
      <el-table-column prop="title" label="标题" />
      <el-table-column prop="words" label="字数" width="100" />
      <el-table-column prop="status" label="状态" width="120" />
      <el-table-column label="操作" width="160">
        <template #default>
          <el-button size="small" text type="primary">查看</el-button>
          <el-button size="small" text>备注</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-card class="stub-note" shadow="never">
      <p>后端接口（待实现）：<code>GET /api/v1/projects/{id}/chapters</code></p>
    </el-card>
  </div>
</template>

<script setup></script>

<style scoped>
.stub-title { margin: 0 0 16px; }
.stub-note { margin-top: 16px; }
.stub-note code { background: #f4f4f5; padding: 2px 6px; border-radius: 4px; }
</style>
