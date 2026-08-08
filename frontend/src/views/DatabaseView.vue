<template>
  <div class="db">
    <!-- 工具条 -->
    <div class="db-toolbar">
      <div class="db-title">
        资料库 · 角色库
        <span class="db-novel">当前作品：{{ store.currentNovel?.name || '未选择' }}</span>
      </div>
      <div class="db-toolbar-actions">
        <el-button :icon="Share" @click="goRelation">关系网</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建角色</el-button>
      </div>
    </div>

    <!-- 角色表格 -->
    <el-card shadow="never" class="db-card">
      <el-table :data="list" v-loading="loading" empty-text="暂无角色，点击右上角新建" border stripe>
        <el-table-column prop="name" label="姓名" width="120" fixed />
        <el-table-column label="地位" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.role_type" :type="roleTag(row.role_type)" size="small" effect="light">
              {{ row.role_type }}
            </el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="年龄" width="70">
          <template #default="{ row }">{{ row.age ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="性别" width="70">
          <template #default="{ row }">{{ row.gender || '—' }}</template>
        </el-table-column>
        <el-table-column label="当前等级" width="130">
          <template #default="{ row }">{{ row.current_level || '—' }}</template>
        </el-table-column>
        <el-table-column label="性格" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.personality || '—' }}</template>
        </el-table-column>
        <el-table-column label="简介" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.brief || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" text type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建 / 编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑角色' : '新建角色'"
      width="760px"
      top="4vh"
      @closed="resetForm"
    >
      <CharacterForm v-model="form" />
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
import { Plus, Share } from '@element-plus/icons-vue'
import { useProjectStore } from '@/store/project'
import { characterApi } from '@/api/database'
import CharacterForm from '@/components/database/CharacterForm.vue'
import { useRouter } from 'vue-router'

const store = useProjectStore()
const projectId = computed(() => store.currentNovelId)
const router = useRouter()
function goRelation() { router.push('/workspace/character-relation') }

const list = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)

const emptyForm = () => ({
  name: '',
  role_type: null,
  age: null,
  gender: null,
  current_level: '',
  personality: '',
  background: '',
  talent: '',
  skills: [],
  relationship_network: [],
  brief: '',
})
const form = reactive(emptyForm())

const roleTag = (t) => ({ '主角': 'danger', '配角': 'warning', '反派': 'info' }[t] || 'info')

async function load() {
  if (!projectId.value) return
  loading.value = true
  try {
    list.value = await characterApi.list(projectId.value)
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
    role_type: row.role_type,
    age: row.age,
    gender: row.gender,
    current_level: row.current_level,
    personality: row.personality,
    background: row.background,
    talent: row.talent,
    skills: row.skills ? [...row.skills] : [],
    relationship_network: row.relationship_network ? [...row.relationship_network] : [],
    brief: row.brief,
  })
  editingId.value = row.id
  dialogVisible.value = true
}

async function save() {
  if (!form.name || !form.name.trim()) {
    ElMessage.warning('请填写角色姓名')
    return
  }
  const payload = { ...form }
  if (editingId.value) {
    await characterApi.update(projectId.value, editingId.value, payload)
    ElMessage.success('已更新')
  } else {
    await characterApi.create(projectId.value, payload)
    ElMessage.success('已创建')
  }
  dialogVisible.value = false
  load()
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除角色「${row.name}」？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await characterApi.remove(projectId.value, row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
// 切换作品时重新加载角色
watch(projectId, load)
</script>

<style scoped>
.db { padding: 4px; }
.db-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.db-title { font-size: 16px; font-weight: 600; }
.db-novel { font-size: 13px; color: #909399; font-weight: 400; margin-left: 10px; }
.db-toolbar-actions { display: flex; gap: 10px; }
.db-card { margin-bottom: 14px; }
.muted { color: #c0c4cc; }
</style>
