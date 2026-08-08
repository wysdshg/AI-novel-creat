<template>
  <div class="ref-view">
    <div class="ref-head">
      <div>
        <h3>参考文档</h3>
        <p class="ref-tip">
          为当前小说上传参考素材（大纲、设定笔记、同人资料、背景资料等），AI 生成章节时会自动读取这些文本作为上下文。
          支持 <b>.txt / .md / .json / .csv / .log</b> 等文本文件；PDF / Word 等二进制解析后续扩展。
        </p>
      </div>
      <el-upload
        class="ref-upload"
        :auto-upload="false"
        :show-file-list="false"
        :disabled="!currentNovelId"
        :on-change="onFileChange"
        accept=".txt,.md,.markdown,.json,.csv,.log,.text"
      >
        <el-button type="primary" :disabled="!currentNovelId">
          <el-icon><UploadFilled /></el-icon> 上传文档
        </el-button>
      </el-upload>
    </div>

    <el-alert
      v-if="!currentNovelId"
      type="info"
      :closable="false"
      title="请先在左侧选择或新建一本小说"
      style="margin-bottom: 12px"
    />

    <el-table v-else :data="docs" border stripe style="width: 100%">
      <el-table-column prop="filename" label="文件名" min-width="200" />
      <el-table-column label="类型" width="120">
        <template #default="{ row }">{{ row.content_type }}</template>
      </el-table-column>
      <el-table-column label="大小" width="110">
        <template #default="{ row }">{{ formatSize(row.size) }}</template>
      </el-table-column>
      <el-table-column label="上传时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="previewDoc(row)">查看</el-button>
          <el-button size="small" type="danger" @click="removeDoc(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="currentNovelId && !docs.length" description="暂无参考文档，点右上角上传" />

    <!-- 查看正文弹窗 -->
    <el-dialog v-model="previewVisible" :title="previewDocName" width="70%">
      <pre class="ref-preview">{{ previewText }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useProjectStore } from '@/store/project'
import { referenceApi } from '@/api/reference'

const store = useProjectStore()
const currentNovelId = computed(() => store.currentNovelId)

const docs = ref([])
const loading = ref(false)
const previewVisible = ref(false)
const previewDocName = ref('')
const previewText = ref('')

async function loadDocs() {
  if (!currentNovelId.value) { docs.value = []; return }
  loading.value = true
  try {
    docs.value = await referenceApi.list(currentNovelId.value)
  } catch {
    docs.value = []
  } finally {
    loading.value = false
  }
}

function onFileChange(file) {
  const raw = file.raw
  if (!raw) return
  if (!currentNovelId.value) { ElMessage.warning('请先选择小说'); return }
  const reader = new FileReader()
  reader.onload = async () => {
    const text = String(reader.result || '')
    try {
      await referenceApi.upload(currentNovelId.value, {
        filename: raw.name,
        content_type: raw.type || 'text/plain',
        size: raw.size,
        content_text: text,
      })
      ElMessage.success(`已上传：${raw.name}`)
      await loadDocs()
    } catch (e) {
      ElMessage.error('上传失败：' + (e?.message || '未知错误'))
    }
  }
  reader.onerror = () => ElMessage.error('读取文件失败')
  reader.readAsText(raw)
}

async function previewDoc(row) {
  try {
    const full = await referenceApi.get(currentNovelId.value, row.id)
    previewDocName.value = row.filename
    previewText.value = full.content_text || ''
    previewVisible.value = true
  } catch (e) {
    ElMessage.error('读取失败：' + (e?.message || '未知错误'))
  }
}

async function removeDoc(row) {
  try {
    await ElMessageBox.confirm(`确定删除参考文档「${row.filename}」吗？`, '删除', { type: 'warning' })
  } catch {
    return
  }
  try {
    await referenceApi.remove(currentNovelId.value, row.id)
    ElMessage.success('已删除')
    await loadDocs()
  } catch (e) {
    ElMessage.error('删除失败：' + (e?.message || '未知错误'))
  }
}

function formatSize(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  if (bytes < k) return bytes + ' B'
  if (bytes < k * k) return (bytes / k).toFixed(1) + ' KB'
  return (bytes / (k * k)).toFixed(1) + ' MB'
}

function formatTime(s) {
  if (!s) return ''
  const d = new Date(s)
  return d.toLocaleString('zh-CN', { hour12: false })
}

onMounted(loadDocs)
// 切换小说时自动刷新列表
watch(currentNovelId, loadDocs)
</script>

<style scoped>
.ref-view { padding: 4px; }
.ref-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; }
.ref-head h3 { margin: 0 0 6px; }
.ref-tip { margin: 0; color: #909399; font-size: 13px; line-height: 1.6; max-width: 760px; }
.ref-preview {
  max-height: 60vh; overflow: auto; white-space: pre-wrap; word-break: break-all;
  font-family: monospace; font-size: 13px; background: #f7f7f7; padding: 12px; border-radius: 6px;
}
</style>
