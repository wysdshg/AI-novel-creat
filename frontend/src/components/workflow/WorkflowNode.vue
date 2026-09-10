<template>
  <div
    class="wf-node"
    :class="[`wf-node-${data.nodeType}`, `wf-node-${data.status || 'idle'}`]"
    :title="meta?.description || ''"
  >
    <Handle type="target" :position="Position.Left" />
    <div class="wf-node-body">
      <span class="wf-node-icon">{{ icon }}</span>
      <div class="wf-node-text">
        <div class="wf-node-title">{{ data.label || '未命名' }}</div>
        <div class="wf-node-type">{{ meta?.label || data.nodeType }}</div>
      </div>
    </div>
    <Handle type="source" :position="Position.Right" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

const props = defineProps({
  data: { type: Object, default: () => ({}) },
})

const NODE_META_BY_TYPE = {
  start: { label: '开始', icon: '始' },
  end: { label: '结束', icon: '止' },
  llm: { label: '大模型', icon: 'AI' },
  'setting-retrieval': { label: '设定检索', icon: '设' },
  'if-else': { label: '条件分支', icon: '分' },
  code: { label: '代码执行', icon: '码' },
  template: { label: '模板转换', icon: '模' },
  chapter: { label: '章节生成', icon: '章' },
}

const meta = computed(() => NODE_META_BY_TYPE[props.data.nodeType] || {})
const icon = computed(() => meta.value.icon || '？')
</script>

<style scoped>
.wf-node {
  min-width: 148px;
  max-width: 190px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1.5px solid #dcdfe6;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  font-size: 12px;
  transition: box-shadow 0.15s, border-color 0.15s;
}
.wf-node:hover { box-shadow: 0 2px 10px rgba(0, 0, 0, 0.14); }
.wf-node-body { display: flex; align-items: center; gap: 8px; }
.wf-node-icon {
  flex: 0 0 26px;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
}
.wf-node-text { min-width: 0; }
.wf-node-title { font-weight: 600; color: #303133; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wf-node-type { color: #909399; font-size: 11px; margin-top: 1px; }

/* —— 类型配色 —— */
.wf-node-start .wf-node-icon, .wf-node-end .wf-node-icon { background: #409eff; }
.wf-node-llm .wf-node-icon, .wf-node-setting-retrieval .wf-node-icon { background: #8b5cf6; }
.wf-node-if-else .wf-node-icon { background: #e6a23c; }
.wf-node-code .wf-node-icon, .wf-node-template .wf-node-icon { background: #67c23a; }
.wf-node-chapter .wf-node-icon { background: #f56c6c; }

.wf-node-start { border-color: #a0cfff; }
.wf-node-end { border-color: #a0cfff; }
.wf-node-llm, .wf-node-setting-retrieval { border-color: #c4b5fd; }
.wf-node-if-else { border-color: #f3d19e; }
.wf-node-code, .wf-node-template { border-color: #b3e19d; }
.wf-node-chapter { border-color: #f3a6a6; }

/* —— 运行状态 —— */
.wf-node-running { border-color: #409eff !important; box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.25); animation: wf-pulse 1.2s ease-in-out infinite; }
.wf-node-success { border-color: #67c23a !important; box-shadow: 0 0 0 2px rgba(103, 194, 58, 0.25); }
.wf-node-failed { border-color: #f56c6c !important; box-shadow: 0 0 0 3px rgba(245, 108, 108, 0.3); }
.wf-node-skipped { opacity: 0.45; border-style: dashed; }
@keyframes wf-pulse {
  0%, 100% { box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.25); }
  50% { box-shadow: 0 0 0 6px rgba(64, 158, 255, 0.12); }
}
</style>
