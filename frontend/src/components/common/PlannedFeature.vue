<template>
  <!--
    统一的「规划中」占位页（Phase 1.5）。

    为什么要有这个组件：原先几个未实现的功能页各自写了一套"假 UI"——
    空表格还带"查看/备注"按钮、能点的模板卡片、`el-empty` 写"暂无数据"，
    看起来像"功能有了只是没数据"，实际是根本没实现。作者会误以为功能可用。

    现在统一为：**明确标注「规划中」+ 说明计划做什么 + 不提供任何假交互**。
  -->
  <div class="planned">
    <div class="planned-head">
      <h2 class="planned-title">{{ title }}</h2>
      <el-tag type="warning" effect="plain" size="small">规划中 · 尚未实现</el-tag>
    </div>

    <el-alert type="info" :closable="false" show-icon :title="summary">
      <p v-if="detail" class="planned-detail">{{ detail }}</p>
    </el-alert>

    <el-card class="planned-card" shadow="never">
      <p class="planned-card-title">计划中的能力</p>
      <ul class="planned-list">
        <li v-for="(f, i) in features" :key="i">{{ f }}</li>
      </ul>
      <p v-if="api" class="planned-api">
        后端接口（待接入）：<code>{{ api }}</code>
      </p>
    </el-card>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  summary: { type: String, default: '' },
  detail: { type: String, default: '' },
  features: { type: Array, default: () => [] },
  api: { type: String, default: '' },
})
</script>

<style scoped>
.planned { padding: 4px 2px; }
.planned-head { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.planned-title { margin: 0; font-size: 17px; font-weight: 600; }
.planned-detail { margin: 6px 0 0; line-height: 1.7; }
.planned-card { margin-top: 14px; }
.planned-card-title { margin: 0 0 8px; font-weight: 600; font-size: 13px; }
.planned-list { margin: 0; padding-left: 18px; line-height: 1.9; }
.planned-api { margin: 12px 0 0; font-size: 12px; opacity: 0.75; }
.planned-api code { background: #f4f4f5; padding: 2px 6px; border-radius: 4px; }
</style>
