<template>
  <div class="ov">
    <el-empty v-if="!novel" description="请先在左侧选择或新建一本小说" />

    <template v-else>
      <!-- 小说级 -->
      <section class="ov-block ov-novel">
        <div class="ov-block-head">
          <el-icon class="ov-ic"><Files /></el-icon>
          <h2 class="ov-title">{{ novel.name }}</h2>
          <el-tag v-if="novel.genre" size="small" effect="plain">{{ novel.genre }}</el-tag>
          <el-button class="ov-edit-btn" text type="primary" :icon="Edit" @click="startEdit('novel', novel.id, novel.summary)">编辑</el-button>
        </div>
        <div class="ov-summary">
          <div class="ov-summary-label">AI 概览</div>
          <template v-if="isEditing('novel', novel.id)">
            <el-input v-model="draft" type="textarea" :rows="4" placeholder="填写或修订小说总概览" />
            <div class="ov-edit-actions">
              <el-button size="small" type="primary" :loading="saving" @click="saveEdit">保存</el-button>
              <el-button size="small" @click="cancelEdit">取消</el-button>
            </div>
          </template>
          <p v-else-if="novel.summary" class="ov-summary-text">{{ novel.summary }}</p>
          <p v-else class="ov-empty">暂无 AI 概览。完成卷/篇/章后，此处汇总为小说总概览。</p>
        </div>
      </section>

      <!-- 卷 → 篇 层级 -->
      <section v-for="vol in volumes" :key="vol.id" class="ov-block ov-volume">
        <div class="ov-block-head">
          <el-icon class="ov-ic"><Notebook /></el-icon>
          <h3 class="ov-title">{{ vol.name }}</h3>
          <el-button class="ov-edit-btn" text type="primary" :icon="Edit" @click="startEdit('volume', vol.id, vol.summary)">编辑</el-button>
        </div>
        <div class="ov-summary">
          <div class="ov-summary-label">卷 · AI 概览</div>
          <template v-if="isEditing('volume', vol.id)">
            <el-input v-model="draft" type="textarea" :rows="3" placeholder="填写或修订本卷概览" />
            <div class="ov-edit-actions">
              <el-button size="small" type="primary" :loading="saving" @click="saveEdit">保存</el-button>
              <el-button size="small" @click="cancelEdit">取消</el-button>
            </div>
          </template>
          <p v-else-if="vol.summary" class="ov-summary-text">{{ vol.summary }}</p>
          <p v-else class="ov-empty">本卷暂无 AI 概览（篇章完成后自动汇总）。</p>
        </div>

        <div v-for="art in vol.articles || []" :key="art.id" class="ov-block ov-article">
          <div class="ov-block-head">
            <el-icon class="ov-ic"><Collection /></el-icon>
            <h4 class="ov-title">{{ art.name }}</h4>
            <el-button class="ov-edit-btn" text type="primary" :icon="Edit" @click="startEdit('article', art.id, art.summary)">编辑</el-button>
          </div>
          <div class="ov-summary">
            <div class="ov-summary-label">篇 · AI 概览</div>
            <template v-if="isEditing('article', art.id)">
              <el-input v-model="draft" type="textarea" :rows="3" placeholder="填写或修订本篇概览" />
              <div class="ov-edit-actions">
                <el-button size="small" type="primary" :loading="saving" @click="saveEdit">保存</el-button>
                <el-button size="small" @click="cancelEdit">取消</el-button>
              </div>
            </template>
            <p v-else-if="art.summary" class="ov-summary-text">{{ art.summary }}</p>
            <p v-else class="ov-empty">本篇暂无 AI 概览（完成本章生成后更新）。</p>
          </div>
        </div>

        <el-empty v-if="!(vol.articles || []).length" :image-size="40" description="本卷下还没有篇" />
      </section>

      <el-empty v-if="!volumes.length" :image-size="48" description="还没有卷，去左侧树加一本卷吧" />

      <!-- 更新流说明 -->
      <el-alert
        class="ov-note"
        type="info"
        :closable="false"
        show-icon
        title="概览更新规则"
        description="完成一章生成后更新「篇」内容；篇章完成后更新「卷」内容；卷完成后汇总为小说总概览。以上概览均可在右侧「编辑」按钮处手动修订。"
      />
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Edit, Files, Notebook, Collection } from '@element-plus/icons-vue'
import { useProjectStore } from '@/store/project'
import { projectApi } from '@/api/projects'
import { volumeApi } from '@/api/volume'
import { articleApi } from '@/api/article'

const store = useProjectStore()
const novel = computed(() => store.currentNovel)
const volumes = computed(() => store.structure.volumes || [])

// —— 内联编辑状态（同一时刻仅一处编辑）——
const editing = ref(null)   // { kind: 'novel'|'volume'|'article', id }
const draft = ref('')
const saving = ref(false)

function isEditing(kind, id) {
  return editing.value && editing.value.kind === kind && editing.value.id === id
}
function startEdit(kind, id, current) {
  editing.value = { kind, id }
  draft.value = current || ''
}
function cancelEdit() {
  editing.value = null
  draft.value = ''
}

async function saveEdit() {
  if (!editing.value) return
  const { kind, id } = editing.value
  const projectId = store.currentNovelId
  const payload = { summary: draft.value }
  saving.value = true
  try {
    if (kind === 'novel') {
      await projectApi.update(id, payload)
      const n = store.novels.find((x) => x.id === id)
      if (n) n.summary = draft.value
    } else if (kind === 'volume') {
      await volumeApi.update(projectId, id, payload)
      const v = store.structure.volumes.find((x) => x.id === id)
      if (v) v.summary = draft.value
    } else if (kind === 'article') {
      await articleApi.update(projectId, id, payload)
      for (const v of store.structure.volumes) {
        const a = (v.articles || []).find((x) => x.id === id)
        if (a) { a.summary = draft.value; break }
      }
    }
    ElMessage.success('已保存概览')
    editing.value = null
    draft.value = ''
  } catch (e) {
    ElMessage.error('保存失败：' + (e?.message || '未知错误'))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.ov { padding: 4px; max-width: 920px; }
.ov-block {
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 16px 18px;
  margin-bottom: 14px;
}
.ov-block-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.ov-ic { color: #ff4d4f; }
.ov-title { margin: 0; }
.ov-novel .ov-title { font-size: 22px; }
.ov-volume > .ov-title { font-size: 18px; }
.ov-article { margin-top: 12px; padding: 12px 14px; background: #fafafa; border-style: dashed; }
.ov-article .ov-title { font-size: 15px; }
.ov-edit-btn { margin-left: auto; }
.ov-summary-label {
  display: inline-block; font-size: 12px; color: #909399;
  background: #f4f4f5; padding: 2px 8px; border-radius: 4px; margin-bottom: 6px;
}
.ov-summary-text { margin: 0; line-height: 1.8; color: #303133; white-space: pre-wrap; }
.ov-empty { margin: 0; color: #c0c4cc; font-size: 13px; }
.ov-edit-actions { margin-top: 8px; display: flex; gap: 8px; }
.ov-note { margin-top: 4px; }
</style>
