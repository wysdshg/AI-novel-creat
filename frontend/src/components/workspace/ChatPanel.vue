<template>
  <div class="cp">
    <el-scrollbar class="cp-body" ref="scrollRef">
      <div v-if="!messages.length" class="cp-empty">
        开始和 AI 讨论本章剧情吧～
      </div>
      <div
        v-for="(m, i) in messages"
        :key="i"
        class="cp-msg"
        :class="m.role"
      >
        <div class="cp-avatar">{{ m.role === 'user' ? '我' : 'AI' }}</div>
        <div class="cp-bubble">
          <details v-if="m.thinking" class="cp-think" open>
            <summary>💡 思考过程（模型推理）</summary>
            <div class="cp-think-body">{{ m.thinking }}</div>
          </details>
          <div v-if="m.content" class="cp-answer">{{ m.content }}</div>
          <div v-else-if="m.role === 'ai' && m.thinking" class="cp-answer cp-answer--pending">
            正在思考并组织回答…
          </div>
        </div>
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup>
defineProps({
  messages: { type: Array, default: () => [] },
})
</script>

<style scoped>
.cp {
  height: 100%;
  background: #fff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  overflow: hidden;
}
.cp-body { height: 100%; padding: 16px; }
.cp-empty { color: #909399; text-align: center; margin-top: 40px; }
.cp-msg {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  align-items: flex-start;
}
.cp-msg.ai { flex-direction: row; }
.cp-msg.user { flex-direction: row-reverse; }
.cp-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #fff;
}
.cp-msg.user .cp-avatar { background: #409eff; }
.cp-msg.ai .cp-avatar { background: #67c23a; }
.cp-bubble {
  max-width: 70%;
  padding: 10px 14px;
  border-radius: 10px;
  background: #f4f4f5;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.cp-msg.user .cp-bubble { background: #ecf5ff; }
.cp-think {
  margin-bottom: 8px;
  border: 1px dashed var(--el-border-color);
  border-radius: 8px;
  padding: 6px 10px;
  background: #fafafa;
}
.cp-think summary {
  cursor: pointer;
  font-size: 12px;
  color: #909399;
  user-select: none;
}
.cp-think-body {
  margin-top: 6px;
  max-height: 240px;
  overflow-y: auto;
  font-size: 12px;
  color: #909399;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.55;
}
.cp-answer { white-space: pre-wrap; word-break: break-word; }
.cp-answer--pending { color: #c0c4cc; font-style: italic; }
</style>
