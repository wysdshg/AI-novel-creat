<template>
  <div class="sk">
    <div class="sk-toolbar">
      <div class="sk-title">
        写作 SKILL
        <span class="sk-sub">全局共享 · AI 在调用时会自动注入 prompt_body</span>
      </div>
      <div class="sk-toolbar-actions">
        <el-input
          v-model="keyword"
          placeholder="搜索：名称 / 描述 / 标签"
          clearable
          style="width: 240px"
          @input="load"
          @clear="load"
        />
        <el-select
          v-model="trigger"
          placeholder="全部场景"
          clearable
          style="width: 140px"
          @change="load"
        >
          <el-option v-for="t in triggers" :key="t.v" :label="t.l" :value="t.v" />
        </el-select>
        <el-checkbox v-model="enabledOnly" @change="load">仅启用</el-checkbox>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建 SKILL</el-button>
      </div>
    </div>

    <el-card shadow="never" class="sk-card">
      <el-table :data="list" v-loading="loading" empty-text="还没有 SKILL，先新建一个吧" border stripe>
        <el-table-column prop="name" label="名称" min-width="160" fixed />
        <el-table-column label="调用场景" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="triggerTag(row.trigger)" effect="plain">
              {{ triggerText(row.trigger) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.enabled" type="success" size="small" effect="plain">已启用</el-tag>
            <el-tag v-else type="info" size="small" effect="plain">已停用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标签" min-width="160">
          <template #default="{ row }">
            <el-tag
              v-for="t in (row.tags || []).slice(0, 4)"
              :key="t"
              size="small"
              effect="plain"
              class="sk-tag"
            >{{ t }}</el-tag>
            <span v-if="!row.tags || !row.tags.length" class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" text :type="row.enabled ? 'warning' : 'success'" @click="toggle(row)">
              {{ row.enabled ? '停用' : '启用' }}
            </el-button>
            <el-button size="small" text type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑 SKILL' : '新建 SKILL'"
      width="760px"
      top="6vh"
      @closed="resetForm"
    >
      <el-form :model="form" label-width="110px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="80" show-word-limit />
        </el-form-item>
        <el-form-item label="调用场景">
          <el-select v-model="form.trigger" style="width: 200px">
            <el-option v-for="t in triggers" :key="t.v" :label="t.l" :value="t.v" />
          </el-select>
          <span class="sk-hint">all=全部阶段；也可单独指定 chapter / discussion / memory / parse</span>
        </el-form-item>
        <el-form-item label="提示词正文">
          <el-input
            v-model="form.prompt_body"
            type="textarea"
            :rows="8"
            placeholder="调用本 SKILL 时将本段拼入 AI 提示词上下文..."
          />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="tagsText" placeholder="逗号分隔" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
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
import { customSkillApi } from '@/api/customSkill'

const triggers = [
  { v: 'all', l: '全部场景' },
  { v: 'discussion', l: '对话商讨' },
  { v: 'chapter', l: '章节生成' },
  { v: 'memory', l: '记忆压缩' },
  { v: 'parse', l: '设定解析' },
]
const triggerText = (v) => (triggers.find((t) => t.v === v) || { l: '全部场景' }).l
const triggerTag = (v) => ({
  all: 'success', discussion: 'info', chapter: 'warning', memory: 'danger', parse: '',
}[v] || '')

const keyword = ref('')
const trigger = ref('')
const enabledOnly = ref(false)
const list = ref([])
const loading = ref(false)

const dialogVisible = ref(false)
const editingId = ref(null)
const emptyForm = () => ({
  name: '',
  description: '',
  prompt_body: '',
  trigger: 'all',
  enabled: true,
  tags: [],
})
const form = reactive(emptyForm())
const tagsText = computed({
  get: () => (form.tags || []).join(','),
  set: (v) => { form.tags = String(v || '').split(',').map((s) => s.trim()).filter(Boolean) },
})

async function load() {
  loading.value = true
  try {
    list.value = await customSkillApi.list({
      keyword: keyword.value,
      trigger: trigger.value,
      enabled_only: enabledOnly.value,
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
    prompt_body: row.prompt_body || '',
    trigger: row.trigger || 'all',
    enabled: !!row.enabled,
    tags: Array.isArray(row.tags) ? [...row.tags] : [],
  })
  editingId.value = row.id
  dialogVisible.value = true
}

async function save() {
  if (!form.name || !form.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  if (editingId.value) {
    await customSkillApi.update(editingId.value, form)
    ElMessage.success('已更新')
  } else {
    await customSkillApi.create(form)
    ElMessage.success('已创建')
  }
  dialogVisible.value = false
  load()
}

async function toggle(row) {
  await customSkillApi.update(row.id, { enabled: !row.enabled })
  ElMessage.success(row.enabled ? '已停用' : '已启用')
  load()
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除 SKILL「${row.name}」？`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch { return }
  await customSkillApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
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
.sk-sub { font-size: 13px; color: #909399; font-weight: 400; }
.sk-toolbar-actions { display: flex; gap: 10px; align-items: center; }
.sk-card { margin-bottom: 14px; }
.sk-tag { margin-right: 4px; }
.sk-hint { font-size: 12px; color: #909399; margin-left: 12px; }
.muted { color: #c0c4cc; }
</style>
