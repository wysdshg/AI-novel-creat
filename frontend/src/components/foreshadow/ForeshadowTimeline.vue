<template>
  <el-timeline class="na-tl">
    <el-timeline-item
      v-for="(f, i) in items"
      :key="i"
      :type="f.status === 'done' ? 'success' : f.status === 'active' ? 'warning' : 'info'"
      :timestamp="`第 ${f.buried_chapter ?? '?'} 章埋下`"
    >
      <span class="na-stub-tip">{{ f.description || '伏笔占位' }}</span>
      <el-tag size="small" :type="f.status === 'done' ? 'success' : 'info'">{{ f.status }}</el-tag>
    </el-timeline-item>
    <el-timeline-item v-if="!items.length" type="info" timestamp="—">
      <span class="na-stub-tip">暂无伏笔（脚手架占位）</span>
    </el-timeline-item>
  </el-timeline>
</template>

<script setup>
// 接收 foreshadowApi.list 的标准伏笔数据，渲染进度时间轴。
defineProps({ items: { type: Array, default: () => [] } })
</script>

<style scoped>
.na-tl { padding: 8px; }
</style>
