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
          <!-- 章后走向建议：渲染成可点选的卡片，而不是一坨文字 -->
          <div v-if="isDirections(m)" class="cp-dirs">
            <div class="cp-dirs-head">
              第 {{ m.meta.chapter_no }} 章写完了 · 接下来可以这么走
            </div>
            <div
              v-for="(d, k) in m.meta.directions"
              :key="k"
              class="cp-dir"
              :class="tensionClass(d.tension)"
              @click="$emit('pick-direction', d, m)"
            >
              <div class="cp-dir-top">
                <span class="cp-dir-title">{{ d.title }}</span>
                <span class="cp-dir-tension">张力{{ d.tension || '中' }}</span>
              </div>
              <div class="cp-dir-detail">{{ d.detail }}</div>
            </div>
            <div class="cp-dirs-foot">点一条即可把它写进下一章的商讨</div>
          </div>

          <!-- AI 对话中识别的新实体：一键确认写入资料库（含属性预览） -->
          <div v-else-if="isEntitySuggestion(m)" class="cp-entity-suggest">
            <div class="cp-entity-head">🔍 AI 识别到以下新设定，确认后写入资料库：</div>
            <div
              v-for="(item, k) in m.meta.items"
              :key="k"
              class="cp-entity-card"
            >
              <div class="cp-entity-card-header">
                <el-tag size="small" effect="plain" :type="entityTagType(item.kind)">
                  {{ entityLabel(item.kind) }}
                </el-tag>
                <span class="cp-entity-name">{{ item.name }}</span>
              </div>
              <!-- 角色属性预览 -->
              <div v-if="item.kind === 'character' && hasEntityDetails(item)" class="cp-entity-details">
                <div v-if="item.role_type" class="cp-entity-detail-row">
                  <span class="cp-entity-detail-label">类型</span>
                  <span>{{ item.role_type }}</span>
                </div>
                <div v-if="item.gender" class="cp-entity-detail-row">
                  <span class="cp-entity-detail-label">性别</span>
                  <span>{{ item.gender }}</span>
                </div>
                <div v-if="item.age" class="cp-entity-detail-row">
                  <span class="cp-entity-detail-label">年龄</span>
                  <span>{{ item.age }}</span>
                </div>
                <div v-if="item.personality" class="cp-entity-detail-row">
                  <span class="cp-entity-detail-label">性格</span>
                  <span>{{ item.personality }}</span>
                </div>
                <div v-if="item.talent" class="cp-entity-detail-row">
                  <span class="cp-entity-detail-label">天赋</span>
                  <span>{{ item.talent }}</span>
                </div>
                <div v-if="item.background" class="cp-entity-detail-row">
                  <span class="cp-entity-detail-label">背景</span>
                  <span>{{ item.background }}</span>
                </div>
                <div v-if="item.skills?.length" class="cp-entity-detail-row">
                  <span class="cp-entity-detail-label">技能</span>
                  <span>{{ item.skills.join('、') }}</span>
                </div>
                <div v-if="item.relationship_network?.length" class="cp-entity-detail-row">
                  <span class="cp-entity-detail-label">关系</span>
                  <span>{{ item.relationship_network.join('、') }}</span>
                </div>
                <div v-if="item.brief && !item.personality" class="cp-entity-detail-row">
                  <span class="cp-entity-detail-label">简介</span>
                  <span>{{ item.brief }}</span>
                </div>
              </div>
              <!-- 势力/地点描述预览 -->
              <div v-else-if="item.description" class="cp-entity-details">
                <div class="cp-entity-detail-row">
                  <span>{{ item.description }}</span>
                </div>
              </div>
            </div>
            <el-button
              type="primary"
              size="small"
              :loading="!!m.meta.confirming"
              :disabled="!!m.meta.confirmed"
              @click="$emit('confirm-entities', m)"
            >{{ m.meta.confirmed ? '✓ 已写入资料库' : '确认写入资料库' }}</el-button>
          </div>

          <template v-else>
            <div v-if="m.content" class="cp-answer">{{ m.content }}</div>
            <div v-else-if="m.role === 'ai' && m.thinking" class="cp-answer cp-answer--pending">
              正在思考并组织回答…
            </div>
          </template>
        </div>
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup>
defineProps({
  messages: { type: Array, default: () => [] },
})
defineEmits(['pick-direction', 'confirm-entities'])

const isDirections = (m) =>
  m?.meta?.type === 'post_chapter_directions' &&
  Array.isArray(m?.meta?.directions) &&
  m.meta.directions.length > 0

const isEntitySuggestion = (m) =>
  m?.meta?.type === 'entity_suggestion' &&
  Array.isArray(m?.meta?.items) &&
  m.meta.items.length > 0

const entityLabel = (kind) =>
  kind === 'character' ? '角色' : kind === 'faction' ? '势力' : '地点'

const entityTagType = (kind) =>
  kind === 'character' ? '' : kind === 'faction' ? 'warning' : 'success'

const hasEntityDetails = (item) =>
  !!(item.personality || item.talent || item.background ||
      item.skills?.length || item.relationship_network?.length || item.brief)

const tensionClass = (t) => {
  if (t === '高') return 'is-high'
  if (t === '低') return 'is-low'
  return 'is-mid'
}
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

/* —— 章后走向卡片 —— */
.cp-dirs { white-space: normal; }
.cp-dirs-head {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}
.cp-dir {
  border: 1px solid var(--el-border-color-light);
  border-left: 3px solid #909399;
  border-radius: 6px;
  background: #fff;
  padding: 8px 10px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: box-shadow .15s, transform .1s;
}
.cp-dir:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, .08);
  transform: translateY(-1px);
}
.cp-dir.is-high { border-left-color: #f56c6c; }
.cp-dir.is-mid { border-left-color: #e6a23c; }
.cp-dir.is-low { border-left-color: #67c23a; }
.cp-dir-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.cp-dir-title { font-weight: 600; font-size: 13px; color: #303133; }
.cp-dir-tension { font-size: 11px; color: #909399; flex-shrink: 0; }
.cp-dir-detail { font-size: 12px; color: #606266; line-height: 1.55; }
.cp-dirs-foot { font-size: 11px; color: #a8abb2; margin-top: 2px; }

/* —— AI 实体建议卡片（含属性预览）—— */
.cp-entity-suggest {
  white-space: normal;
  padding: 8px 0 4px;
}
.cp-entity-head {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
}
.cp-entity-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 8px;
  background: #fafbfc;
}
.cp-entity-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.cp-entity-name {
  font-weight: 600;
  font-size: 13px;
  color: #303133;
}
.cp-entity-details {
  margin-top: 6px;
  padding-left: 2px;
}
.cp-entity-detail-row {
  display: flex;
  gap: 6px;
  font-size: 12px;
  line-height: 1.7;
  color: #606266;
}
.cp-entity-detail-label {
  flex-shrink: 0;
  color: #909399;
  font-weight: 500;
  &::after { content: '：'; }
}
.cp-entity-suggest .el-button {
  margin-top: 4px;
}
</style>
