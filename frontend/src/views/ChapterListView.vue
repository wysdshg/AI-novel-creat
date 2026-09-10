<template>
  <PlannedFeature
    title="章节列表"
    summary="全书章节的汇总视图：字数、状态、备注"
    detail="当前状态：后端章节 CRUD 已完备（列表/详情/增删改都真实可用），
      缺的只是这个页面的接线——表格数据源还是空数组。属于前端待接线，不是后端缺功能。"
    :features="[
      '按卷/篇分组的章节表：标题、字数、状态、更新时间',
      '点击进入该章工作区（对话 + 正文 + 走向）',
      '章节备注与状态标记',
      '批量操作：删除 / 导出',
    ]"
    api="GET /api/v1/projects/{id}/chapters（已就绪，等前端接线）"
  />
</template>

<script setup>
import PlannedFeature from '@/components/common/PlannedFeature.vue'
</script>
