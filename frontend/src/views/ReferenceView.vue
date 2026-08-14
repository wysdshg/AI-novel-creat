<template>
  <div class="ref-view">
    <el-alert
      v-if="!currentNovelId"
      type="info"
      :closable="false"
      title="请先在左侧选择或新建一本小说"
      style="margin-bottom: 12px"
    />

    <template v-else>
      <!-- 参考文档（按小说维度，用户手动上传） -->
      <section class="ref-section">
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
            :on-change="onFileChange"
            accept=".txt,.md,.markdown,.json,.csv,.log,.text"
          >
            <el-button type="primary">
              <el-icon><UploadFilled /></el-icon> 上传文档
            </el-button>
          </el-upload>
        </div>

        <el-table v-if="novelDocs.length" :data="novelDocs" border stripe style="width: 100%">
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
        <el-empty v-else description="暂无参考文档，点右上角上传" :image-size="80" />
      </section>

      <!-- 篇章参考文档（按篇维度，AI 生成章后自动写入，每篇一篇） -->
      <section class="ref-section">
        <div class="ref-head">
          <div>
            <h3>篇章参考文档</h3>
            <p class="ref-tip">
              由 AI 在生成某篇章节后自动汇总写入，按「篇」维度保存，供该篇后续章节生成时参考。
            </p>
          </div>
        </div>

        <el-table v-if="articleDocs.length" :data="articleDocs" border stripe style="width: 100%">
          <el-table-column prop="filename" label="文件名" min-width="160" />
          <el-table-column label="所属篇" min-width="160">
            <template #default="{ row }">{{ articleName(row.article_id) }}</template>
          </el-table-column>
          <el-table-column label="类型" width="120">
            <template #default="{ row }">{{ row.content_type }}</template>
          </el-table-column>
          <el-table-column label="大小" width="110">
            <template #default="{ row }">{{ formatSize(row.size) }}</template>
          </el-table-column>
          <el-table-column label="更新时间" width="180">
            <template #default="{ row }">{{ formatTime(row.updated_at || row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="previewDoc(row)">查看</el-button>
              <el-button size="small" type="danger" @click="removeDoc(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="尚无篇章参考文档（生成章节后自动出现）" :image-size="80" />
      </section>
    </template>

    <!-- 查看正文弹窗 -->
    <el-dialog v-model="previewVisible" :title="previewDocName" width="70%">
      <pre class="ref-preview">{{ previewText }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { useProjectStore } from '@/store/project'
import { referenceApi } from '@/api/reference'

const store = useProjectStore()
const currentNovelId = computed(() => store.currentNovelId)

const docs = ref([])
const loading = ref(false)
const previewVisible = ref(false)
const previewDocName = ref('')
const previewText = ref('')

// 按维度拆分：article_id 为空 = 小说级参考文档；非空 = 篇章参考文档
const novelDocs = computed(() => docs.value.filter((d) => !d.article_id))
const articleDocs = computed(() => docs.value.filter((d) => d.article_id))

// 篇 id → 篇名 映射（来自当前小说 4 级结构）
const articleNameMap = computed(() => {
  const m = {}
  for (const v of store.structure.volumes || []) {
    for (const a of v.articles || []) m[a.id] = a.name
  }
  return m
})
function articleName(id) {
  return (id && articleNameMap.value[id]) || '未知篇'
}

async function loadDocs() {
  if (!currentNovelId.value) { docs.value = []; return }
  loading.value = true
  try {
    // 后端按 project_id 返回全部（含篇章级），前端再按 article_id 拆分
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
    await referenceApi.rename(currentNovelId.value, row.id, newName)
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
  const d = new Date(s)
  return d.toLocaleString('zh-CN', { hour12: false })
}

onMounted(loadDocs)
// 切换小说时自动刷新列表
watch(currentNovelId, loadDocs)
</script>

<style scoped>
.ref-view { padding: 4px; }
.ref-section { margin-bottom: 24px; }
.ref-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; }
.ref-head h3 { margin: 0 0 6px; }
.ref-tip { margin: 0; color: #909399; font-size: 13px; line-height: 1.6; max-width: 760px; }
.ref-preview {
  max-height: 60vh; overflow: auto; white-space: pre-wrap; word-break: break-all;
  font-family: monospace; font-size: 13px; background: #f7f7f7; padding: 12px; border-radius: 6px;
}
</style>
