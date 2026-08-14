<template>
  <div class="gref-view">
    <div class="gref-head">
      <div>
        <h3>参考资料（全局共享池）</h3>
        <p class="gref-tip">
          这里是<strong>所有小说共享</strong>的参考资料库。在「新建小说」时可从中挑选若干篇，复制进该小说作为它的参考文档。
          支持 <b>.txt / .md / .json / .csv / .log</b> 等文本文件；PDF / Word 等二进制解析后续扩展。
        </p>
      </div>
      <el-upload
        class="gref-upload"
        :auto-upload="false"
        :show-file-list="false"
        :on-change="onFileChange"
        accept=".txt,.md,.markdown,.json,.csv,.log,.text"
      >
        <el-button type="primary">
          <el-icon><UploadFilled /></el-icon> 上传到全局池
        </el-button>
      </el-upload>
    </div>

    <el-table :data="docs" border stripe style="width: 100%">
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
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="previewDoc(row)">查看</el-button>
          <el-button size="small" @click="renameDoc(row)">重命名</el-button>
          <el-button size="small" type="danger" @click="removeDoc(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!docs.length" description="全局池暂无参考资料，点右上角上传" />

    <!-- 查看正文弹窗 -->
    <el-dialog v-model="previewVisible" :title="previewDocName" width="70%">
      <pre class="gref-preview">{{ previewText }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { globalReferenceApi } from '@/api/reference'

const docs = ref([])
const loading = ref(false)
const previewVisible = ref(false)
const previewDocName = ref('')
const previewText = ref('')

async function loadDocs() {
  loading.value = true
  try {
    docs.value = await globalReferenceApi.list()
  } catch {
    docs.value = []
  } finally {
    loading.value = false
  }
}

function onFileChange(file) {
  const raw = file.raw
  if (!raw) return
  const reader = new FileReader()
  reader.onload = async () => {
    const text = String(reader.result || '')
    try {
      await globalReferenceApi.upload({
        filename: raw.name,
        content_type: raw.type || 'text/plain',
        size: raw.size,
        content_text: text,
      })
      ElMessage.success(`已上传到全局池：${raw.name}`)
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
    const full = await globalReferenceApi.get(row.id)
    previewDocName.value = row.filename
    previewText.value = full.content_text || ''
    previewVisible.value = true
  } catch (e) {
    ElMessage.error('读取失败：' + (e?.message || '未知错误'))
  }
}

async function removeDoc(row) {
  try {
    await ElMessageBox.confirm(`确定删除全局参考资料「${row.filename}」吗？（仅从全局池移除，不影响已复制进各小说的副本）`, '删除', { type: 'warning' })
  } catch {
    return
  }
  try {
    await globalReferenceApi.remove(row.id)
    ElMessage.success('已删除')
    await loadDocs()
  } catch (e) {
    ElMessage.error('删除失败：' + (e?.message || '未知错误'))
  }
}

async function renameDoc(row) {
  try {
    const { value } = await ElMessageBox.prompt('请输入新的文件名', '重命名', {
      inputValue: row.filename,
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputValidator: (v) => {
        if (!v || !v.trim()) return '文件名不能为空'
        if (/[\\/:*?"<>|]/.test(v)) return '文件名不能包含以下字符：\\ / : * ? " < > |'
        return true
      },
    })
    const newName = value.trim()
    if (newName === row.filename) return
    await globalReferenceApi.rename(row.id, newName)
    ElMessage.success('已重命名')
    await loadDocs()
  } catch (e) {
    if (e === 'cancel' || (e && e.message === 'cancel')) return
    ElMessage.error('重命名失败：' + (e?.message || '未知错误'))
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
  return new Date(s).toLocaleString('zh-CN', { hour12: false })
}

onMounted(loadDocs)
</script>

<style scoped>
.gref-view { padding: 4px; }
.gref-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; }
.gref-head h3 { margin: 0 0 6px; }
.gref-tip { margin: 0; color: #909399; font-size: 13px; line-height: 1.6; max-width: 760px; }
.gref-preview {
  max-height: 60vh; overflow: auto; white-space: pre-wrap; word-break: break-all;
  font-family: monospace; font-size: 13px; background: #f7f7f7; padding: 12px; border-radius: 6px;
}
</style>
