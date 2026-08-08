<template>
  <div class="na-graph">
    <el-empty description="关系网图谱（三期可视化）">
      <template #description>
        <span class="na-stub-tip">
          关系图谱可视化占位。接收 relationApi.list 的标准关系数据，<br />
          渲染节点（角色/势力）+ 带关系类型/强度的连线。<br />
          可拖拽编辑后批量 relationApi.update 落库。
        </span>
      </template>
    </el-empty>
  </div>
</template>

<script setup>
// 解耦约定：父组件传入 relations 数组（subject_id/object_id/relation_type/strength），
// 组件仅负责渲染，不持有业务状态。
defineProps({ relations: { type: Array, default: () => [] } })
</script>

<style scoped>
.na-graph { min-height: 320px; }
</style>
