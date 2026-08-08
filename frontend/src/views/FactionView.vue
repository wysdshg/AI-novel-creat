<template>
  <div class="db">
    <div class="db-toolbar">
      <div class="db-title">
        资料库 · 势力库
        <span class="db-novel">当前作品：{{ store.currentNovel?.name || '未选择' }}</span>
      </div>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建势力</el-button>
    </div>

    <el-card shadow="never" class="db-card">
      <el-table :data="list" v-loading="loading" empty-text="暂无势力，点击右上角新建" border stripe>
        <el-table-column prop="name" label="名称" width="160" fixed />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.status" :type="statusTag(row.status)" size="small" effect="light">{{ statusText(row.status) }}</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="成员数" width="90" prop="members" :formatter="(r) => (r.members || []).length" />
        <el-table-column label="描述" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" text type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑势力' : '新建势力'"
      width="680px"
      top="6vh"
      @closed="resetForm"
    >
      <FactionForm v-model="form" />
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useProjectStore } from '@/store/project'
import { factionApi } from '@/api/database'
import FactionForm from '@/components/database/FactionForm.vue'

const store = useProjectStore()
const projectId = computed(() => store.currentNovelId)

const list = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)

const emptyForm = () => ({ name: '', description: '', status: null, members: [] })
const form = reactive(emptyForm())

const statusTag = (s) => ({ active: 'success', dormant: 'warning', fallen: 'info' }[s] || 'info')
const statusText = (s) => ({ active: '活跃', dormant: '蛰伏', fallen: '覆灭' }[s] || s)

async function load() {
  if (!projectId.value) return
  loading.value = true
  try {
    const res = await factionApi.list(projectId.value)
    list.value = Array.isArray(res) ? res : (res.items || [])
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
    description: row.description,
    status: row.status,
    members: row.members ? [...row.members] : [],
  })
  editingId.value = row.id
  dialogVisible.value = true
}

async function save() {
  if (!form.name || !form.name.trim()) {
    ElMessage.warning('请填写势力名称')
    return
  }
  const payload = { ...form }
  if (editingId.value) {
    await factionApi.update(projectId.value, editingId.value, payload)
    ElMessage.success('已更新')
  } else {
    await factionApi.create(projectId.value, payload)
    ElMessage.success('已创建')
  }
  dialogVisible.value = false
  load()
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除势力「${row.name}」？`, '删除确认', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
    await factionApi.remove(projectId.value, row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    if (e !== 'cancel' && e?.action !== 'cancel') console.error(e)
  }
}

onMounted(load)
watch(projectId, load)
</script>

<style scoped>
.db { padding: 4px 16px 16px; }
.db-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.db-title { font-size: 18px; font-weight: 600; }
.db-novel { font-size: 13px; font-weight: 400; color: #909399; margin-left: 10px; }
.muted { color: #c0c4cc; }
</style>
