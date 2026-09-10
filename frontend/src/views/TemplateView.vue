<template>
  <PlannedFeature
    title="套路模板"
    summary="网文高频桥段的结构化模板库"
    detail="当前状态：设计方向已定但实现方式仍在考究中，暂时冻结（原 7 条硬编码模板
      题材绑定、不可编辑，与「题材无关」原则冲突，已不再展示）。"
    :features="[
      '可编辑 / 可新增的模板库（不再硬编码）',
      '题材中立的结构化描述：节奏骨架 / 情节节点 / 冲突类型 / 爽点分布',
      '选定模板 + 角色配置 → AI 拆分章节大纲',
      '与工作流打通：模板作为编排起点',
    ]"
    api="POST /api/v1/projects/{id}/templates/generate-outline（待设计定型后实现）"
  />
</template>

<script setup>
import PlannedFeature from '@/components/common/PlannedFeature.vue'
</script>
