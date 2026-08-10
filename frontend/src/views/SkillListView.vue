<template>
  <div class="sk">
    <div class="sk-toolbar">
      <div class="sk-title">
        资料库 · 技能库
        <span class="sk-novel">当前作品：{{ store.currentNovel?.name || '未选择' }}</span>
      </div>
      <div class="sk-toolbar-actions">
        <el-input
          v-model="keyword"
          placeholder="搜索：技能名"
          clearable
          style="width: 220px"
          @input="load"
          @clear="load"
        />
        <el-button :icon="RefreshRight" @click="load">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建技能</el-button>
      </div>
    </div>

    <el-card v-if="!projectId" shadow="never" class="sk-empty">
      <el-alert type="info" :closable="false" title="请先在左侧选择或新建一本小说" />
    </el-card>

    <el-card v-else shadow="never" class="sk-card">
      <el-table
        :data="filteredList"
        v-loading="loading"
        empty-text="暂无技能，点击右上角新建"
        border stripe
      >
        <el-table-column prop="name" label="技能名" min-width="160" fixed />
        <el-table-column label="等级" width="120">
          <template #default="{ row }">{{ row.level || '—' }}</template>
        </el-table-column>
        <el-table-column label="效果" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.effect || '—' }}</template>
        </el-table-column>
        <el-table-column label="限制" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.limitation || '—' }}</template>
        </el-table-column>
        <el-table-column label="副作用" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.side_effect || '—' }}</template>
        </el-table-column>
        <el-table-column label="解锁条件" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.unlock_condition || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" text type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑技能' : '新建技能'"
      width="680px"
      top="6vh"
      @closed="resetForm"
    >
      <el-form :model="form" label-width="100px">
        <el-form-item label="技能名" required>
          <el-input v-model="form.name" maxlength="80" show-word-limit />
        </el-form-item>
        <el-form-item label="等级">
          <el-input v-model="form.level" placeholder="例如：高级 / S 级 / 一阶" />
        </el-form-item>
        <el-form-item label="效果">
          <el-input v-model="form.effect" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="限制">
          <el-input v-model="form.limitation" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="副作用">
          <el-input v-model="form.side_effect" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="解锁条件">
          <el-input v-model="form.unlock_condition" type="textarea" :rows="2" />
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
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, RefreshRight } from '@element-plus/icons-vue'
import { useProjectStore } from '@/store/project'
import { skillApi } from '@/api/database'

const store = useProjectStore()
const projectId = computed(() => store.currentNovelId)
const list = ref([])
const loading = ref(false)
const keyword = ref('')

const dialogVisible = ref(false)
const editingId = ref(null)
const emptyForm = () => ({
  name: '',
  level: '',
  effect: '',
  limitation: '',
  side_effect: '',
  unlock_condition: '',
})
const form = reactive(emptyForm())

const filteredList = computed(() => {
  if (!keyword.value) return list.value
  const k = keyword.value.toLowerCase()
  return list.value.filter((s) => (s.name || '').toLowerCase().includes(k))
})

async function load() {
  if (!projectId.value) {
    list.value = []
    return
  }
  loading.value = true
  try {
    list.value = await skillApi.list(projectId.value)
  } catch (e) {
    list.value = []
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
    level: row.level || '',
    effect: row.effect || '',
    limitation: row.limitation || '',
    side_effect: row.side_effect || '',
    unlock_condition: row.unlock_condition || '',
  })
  editingId.value = row.id
  dialogVisible.value = true
}

async function save() {
  if (!form.name || !form.name.trim()) {
    ElMessage.warning('请填写技能名')
    return
  }
  if (editingId.value) {
    await skillApi.update(projectId.value, editingId.value, form)
    ElMessage.success('已更新')
  } else {
    await skillApi.create(projectId.value, form)
    ElMessage.success('已创建')
  }
  dialogVisible.value = false
  load()
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除技能「${row.name}」？`, '删除确认', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch { return }
  await skillApi.remove(projectId.value, row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
watch(projectId, load)
</script>

<style scoped>
.sk { padding: 4px; }
.sk-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  flex-wrap: wrap;
  gap: 10px;
}
.sk-title { font-size: 16px; font-weight: 600; display: flex; align-items: baseline; gap: 10px; }
.sk-novel { font-size: 13px; color: #909399; font-weight: 400; }
.sk-toolbar-actions { display: flex; gap: 10px; align-items: center; }
.sk-card, .sk-empty { margin-bottom: 14px; }
</style>
