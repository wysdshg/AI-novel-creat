<template>
  <PlannedFeature
    title="线索 / 伏笔"
    summary="伏笔全生命周期管理：埋下 → 追踪 → 回收"
    detail="当前状态：AI 每章已在抽取伏笔动作（存在章级记忆里），但尚未写入伏笔表，
      因此这个页面暂时没有数据可展示。后端回注正在 Phase 2.1 推进。"
    :features="[
      '伏笔列表 + 时间轴：按章号展示埋设与回收节点',
      '状态追踪：未埋 / 已埋 / 已回收 / 已废弃',
      '生成前置检索：本章要点命中未回收伏笔时自动注入提醒',
      '与章节记忆联动：从 AI 抽取结果自动建伏笔（Phase 2.1）',
    ]"
    api="GET /api/v1/projects/{id}/foreshadows（当前为桩，2.1 后转真实）"
  />
</template>

<script setup>
import PlannedFeature from '@/components/common/PlannedFeature.vue'
</script>
