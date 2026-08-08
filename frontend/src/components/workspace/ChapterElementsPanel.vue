<template>
  <div class="cep">
    <div class="cep-title">本章要素</div>
    <el-scrollbar class="cep-body">
      <ChapterElementsForm ref="formRef" />
    </el-scrollbar>
  </div>
</template>

<script setup>
import ChapterElementsForm from './ChapterElementsForm.vue'
</script>

<style scoped>
.cep {
  height: 100%;
  background: #fff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.cep-title {
  padding: 12px 16px;
  font-weight: 600;
  border-bottom: 1px solid var(--el-border-color-light);
}
.cep-body { flex: 1; padding: 12px; }
</style>
