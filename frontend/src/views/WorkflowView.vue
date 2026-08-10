<template>
  <div class="wf">
    <div class="wf-toolbar">
      <div class="wf-title">
        工作流
        <span class="wf-sub">全局共享 · 可视化 DAG 模板（节点 + 边的流程图）</span>
      </div>
      <div class="wf-toolbar-actions">
        <el-input
          v-model="keyword"
          placeholder="搜索：名称 / 描述 / 标签"
          clearable
          style="width: 240px"
          @input="load"
          @clear="load"
        />
        <el-checkbox v-model="activeOnly" @change="load">仅启用</el-checkbox>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建工作流</el-button>
      </div>
    </div>

    <el-card shadow="never" class="wf-card">
      <el-table :data="list" v-loading="loading" empty-text="还没有工作流，先新建一个吧" border stripe>
        <el-table-column prop="name" label="名称" min-width="160" fixed />
        <el-table-column label="节点 / 边" width="130">
          <template #default="{ row }">
            {{ (row.nodes || []).length }} 节点 · {{ (row.edges || []).length }} 边
          </template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.is_active" type="success" size="small" effect="plain">是</el-tag>
            <el-tag v-else type="info" size="small" effect="plain">否</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标签" min-width="160">
          <template #default="{ row }">
            <el-tag
              v-for="t in (row.tags || []).slice(0, 4)"
              :key="t"
              size="small"
              effect="plain"
              class="wf-tag"
            >{{ t }}</el-tag>
            <span v-if="!row.tags || !row.tags.length" class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" text @click="duplicate(row)">复制</el-button>
            <el-button size="small" text :type="row.is_active ? 'warning' : 'success'" @click="toggle(row)">
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
            <el-button size="small" text type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑工作流' : '新建工作流'"
      width="900px"
      top="6vh"
      @closed="resetForm"
    >
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="120" show-word-limit />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="tagsText" placeholder="逗号分隔" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
        <el-form-item label="节点 (nodes)">
          <el-input
            v-model="nodesText"
            type="textarea"
            :rows="8"
            placeholder='JSON 数组，例如：[{"id":"n1","type":"start","label":"开场"},{"id":"n2","type":"step","label":"引入冲突"}]'
          />
        </el-form-item>
        <el-form-item label="边 (edges)">
          <el-input
            v-model="edgesText"
            type="textarea"
            :rows="6"
            placeholder='JSON 数组，例如：[{"from":"n1","to":"n2","condition":"always"}]'
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { workflowApi } from '@/api/workflow'

const keyword = ref('')
const activeOnly = ref(false)
const list = ref([])
const loading = ref(false)

const dialogVisible = ref(false)
const editingId = ref(null)
const emptyForm = () => ({
  name: '',
  description: '',
  tags: [],
  is_active: true,
  nodes: [],
  edges: [],
})
const form = reactive(emptyForm())
const tagsText = computed({
  get: () => (form.tags || []).join(','),
  set: (v) => { form.tags = String(v || '').split(',').map((s) => s.trim()).filter(Boolean) },
})
// JSON 编辑：双向。保存时 parse 失败 → 弹错。
const nodesText = computed({
  get: () => JSON.stringify(form.nodes || [], null, 2),
  set: (v) => {
    try { form.nodes = v.trim() ? JSON.parse(v) : [] }
    catch { form._nodesParseError = true }
  },
})
const edgesText = computed({
  get: () => JSON.stringify(form.edges || [], null, 2),
  set: (v) => {
    try { form.edges = v.trim() ? JSON.parse(v) : [] }
    catch { form._edgesParseError = true }
  },
})

async function load() {
  loading.value = true
  try {
    list.value = await workflowApi.list({
      keyword: keyword.value,
      active_only: activeOnly.value,
    })
  } finally {
    loading.value = false
  }
}

function resetForm() {
  Object.assign(form, emptyForm())
  editingId.value = null
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  Object.assign(form, {
    name: row.name,
    description: row.description || '',
    tags: Array.isArray(row.tags) ? [...row.tags] : [],
    is_active: !!row.is_active,
    nodes: Array.isArray(row.nodes) ? row.nodes : [],
    edges: Array.isArray(row.edges) ? row.edges : [],
  })
  editingId.value = row.id
  dialogVisible.value = true
}

async function save() {
  if (!form.name || !form.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  // 重新触发 parse（computed 是双向，可能没在最新 set 路径走过 set）
  try { form.nodes = nodesText.value.trim() ? JSON.parse(nodesText.value) : [] } catch { ElMessage.error('节点 JSON 解析失败'); return }
  try { form.edges = edgesText.value.trim() ? JSON.parse(edgesText.value) : [] } catch { ElMessage.error('边 JSON 解析失败'); return }
  // 校验：节点 id 唯一；边端点必须存在
  const ids = new Set((form.nodes || []).map((n) => n.id))
  if (ids.size !== (form.nodes || []).length) {
    ElMessage.error('节点 id 必须唯一')
    return
  }
  for (const e of form.edges || []) {
    if (!ids.has(e.from) || !ids.has(e.to)) {
      ElMessage.error(`边 ${e.from} → ${e.to} 端点不存在`)
      return
    }
  }
  if (editingId.value) {
    await workflowApi.update(editingId.value, form)
    ElMessage.success('已更新')
  } else {
    await workflowApi.create(form)
    ElMessage.success('已创建')
  }
  dialogVisible.value = false
  load()
}

async function duplicate(row) {
  await workflowApi.duplicate(row.id)
  ElMessage.success('已复制')
  load()
}

async function toggle(row) {
  await workflowApi.update(row.id, { is_active: !row.is_active })
  ElMessage.success(row.is_active ? '已停用' : '已启用')
  load()
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除工作流「${row.name}」？此操作不可撤销。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch { return }
  await workflowApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>

<style scoped>
.wf { padding: 4px; }
.wf-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  flex-wrap: wrap;
  gap: 10px;
}
.wf-title { font-size: 16px; font-weight: 600; display: flex; align-items: baseline; gap: 10px; }
.wf-sub { font-size: 13px; color: #909399; font-weight: 400; }
.wf-toolbar-actions { display: flex; gap: 10px; align-items: center; }
.wf-card { margin-bottom: 14px; }
.wf-tag { margin-right: 4px; }
.muted { color: #c0c4cc; }
</style>
