<template>
  <div class="sv">
    <div class="sv-toolbar">
      <div class="sv-title">
        设定库
        <span class="sv-sub">全局共享 · 创建小说时可挑选</span>
      </div>
      <div class="sv-toolbar-actions">
        <el-input
          v-model="keyword"
          placeholder="搜索：名称 / 描述 / 标签"
          clearable
          style="width: 240px"
          @input="load"
          @clear="load"
        />
        <el-select
          v-model="category"
          placeholder="全部分类"
          clearable
          style="width: 140px"
          @change="load"
        >
          <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
        </el-select>
        <el-checkbox v-model="templateOnly" @change="load">仅模板</el-checkbox>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建设定</el-button>
      </div>
    </div>

    <!-- 子标签页切换 -->
    <div class="sv-tabs" v-if="hasNovel">
      <span
        class="sv-tab"
        :class="{ 'sv-tab-active': activeTab === 'global' }"
        @click="activeTab = 'global'"
      >全局设定库</span>
      <span
        class="sv-tab"
        :class="{ 'sv-tab-active': activeTab === 'novel' }"
        @click="switchToNovelTab"
      >本小说设定库</span>
    </div>

    <!-- 全局设定库列表（默认视图） -->
    <template v-if="activeTab === 'global'">
    <el-card shadow="never" class="sv-card">
      <el-table :data="list" v-loading="loading" empty-text="还没有设定，先去新建一个吧" border stripe>
        <el-table-column prop="name" label="名称" min-width="160" fixed />
        <el-table-column label="分类" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="等级/条目数" width="120">
          <template #default="{ row }">{{ (row.levels || []).length }}</template>
        </el-table-column>
        <el-table-column label="模板" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.is_template" type="success" size="small" effect="plain">是</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="标签" min-width="160">
          <template #default="{ row }">
            <el-tag
              v-for="t in (row.tags || []).slice(0, 4)"
              :key="t"
              size="small"
              effect="plain"
              class="sv-tag"
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
            <el-button size="small" text type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    </template>

    <!-- 本小说设定库管理（选中小说时显示） -->
    <template v-if="activeTab === 'novel'">
    <el-card shadow="never" class="sv-card">
      <div class="sv-novel-header">
        <span>当前小说：{{ novelName }}</span>
        <el-button size="small" @click="openNovelSettingEditor">修改设定库</el-button>
      </div>

      <!-- 已选设定列表 -->
      <div v-if="novelSettings.length" class="sv-novel-list">
        <div v-for="s in novelSettings" :key="s.id" class="sv-novel-item">
          <span class="sv-novel-name">{{ s.name }}</span>
          <el-tag size="small" effect="plain">{{ s.category }}</el-tag>
          <span class="sv-novel-desc">{{ (s.description || '').slice(0, 80) }}{{ (s.description || '').length > 80 ? '…' : '' }}</span>
        </div>
      </div>
      <el-empty v-else :image-size="60" description="本小说未选择任何设定，对话时将全量注入所有全局设定" />
    </el-card>
    </template>

    <!-- 新建 / 编辑 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑设定' : '新建设定'"
      width="720px"
      top="6vh"
      @closed="resetForm"
    >
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="120" show-word-limit />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" style="width: 200px">
            <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
          </el-select>
        </el-form-item>
        <el-form-item label="等级/条目">
          <el-input
            v-model="levelsText"
            type="textarea"
            :rows="5"
            placeholder="每行一项，例如：炼气 / 筑基 / 金丹 / 元婴 ..."
            @keydown.enter.stop
          />
          <div class="sv-hint">将按行解析为 JSON 数组字符串。{{ (form.levels || []).length }} 项</div>
        </el-form-item>
        <el-form-item label="标签">
          <el-input
            v-model="tagsText"
            placeholder="逗号分隔，例如：玄幻,高武,修炼"
          />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="可被挑选">
          <el-switch v-model="form.is_template" />
          <span class="sv-hint">开启后，「新建小说」可选用本设定</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 本小说设定库编辑弹窗 -->
    <el-dialog
      v-model="novelDialogVisible"
      title="修改本小说设定库"
      width="560px"
      :close-on-click-modal="false"
    >
      <div class="sv-novel-edit-hint">
        勾选的设定将在本小说对话中注入。不勾选任何项 = 全量注入所有全局设定。
      </div>
      <div v-if="novelEditLoading" class="sv-novel-hint" style="text-align:center;padding:20px 0">加载中…</div>
      <el-checkbox-group v-else v-model="novelSelectedIds" class="sv-novel-edit-list">
        <el-checkbox v-for="s in allTemplates" :key="s.id" :value="s.id" class="sv-novel-edit-item">
          <span class="sv-novel-name">{{ s.name }}</span>
          <el-tag size="small" effect="plain">{{ s.category }}</el-tag>
          <span class="sv-novel-meta">{{ (s.levels || []).length }} 级</span>
        </el-checkbox>
      </el-checkbox-group>
      <div v-if="allTemplates.length" class="sv-novel-count">
        已选 {{ novelSelectedIds.length }} / {{ allTemplates.length }}
      </div>
      <template #footer>
        <el-button @click="novelDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="novelSaving" @click="saveNovelSettings">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { settingApi } from '@/api/setting'
import { projectApi } from '@/api/projects'
import { useProjectStore } from '@/store/project'

const store = useProjectStore()
const hasNovel = computed(() => !!store.currentNovelId)
const novelName = computed(() => store.currentNovelName || '未选择')

const categories = ['境界', '货币', '体系', '规则', '其它']
const keyword = ref('')
const category = ref('')
const templateOnly = ref(false)
const list = ref([])
const loading = ref(false)

const dialogVisible = ref(false)
const editingId = ref(null)
const emptyForm = () => ({
  name: '',
  category: '其它',
  levels: [],
  description: '',
  tags: [],
  is_template: false,
})
const form = reactive(emptyForm())
const levelsText = ref('')
watch(levelsText, (v) => {
  form.levels = String(v || '').split('\n').map((s) => s.trim()).filter(Boolean)
})
const tagsText = computed({
  get: () => (form.tags || []).join(','),
  set: (v) => { form.tags = String(v || '').split(',').map((s) => s.trim()).filter(Boolean) },
})

async function load() {
  loading.value = true
  try {
    list.value = await settingApi.list({
      keyword: keyword.value,
      category: category.value,
      template_only: templateOnly.value,
    })
  } finally {
    loading.value = false
  }
}

function resetForm() {
  Object.assign(form, emptyForm())
  levelsText.value = ''
  editingId.value = null
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  Object.assign(form, {
    name: row.name,
    category: row.category || '其它',
    levels: Array.isArray(row.levels) ? [...row.levels] : [],
    description: row.description || '',
    tags: Array.isArray(row.tags) ? [...row.tags] : [],
    is_template: !!row.is_template,
  })
  levelsText.value = Array.isArray(row.levels) ? row.levels.join('\n') : ''
  editingId.value = row.id
  dialogVisible.value = true
}

async function save() {
  if (!form.name || !form.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  if (editingId.value) {
    await settingApi.update(editingId.value, form)
    ElMessage.success('已更新')
  } else {
    await settingApi.create(form)
    ElMessage.success('已创建')
  }
  dialogVisible.value = false
  load()
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除设定「${row.name}」？此操作不可撤销。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch { return }
  await settingApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)

// ====== 本小说设定库管理 ======
const activeTab = ref('global')  // 'global' | 'novel'

// 已选设定详情（含 name/category/description）
const novelSettings = ref([])

// 编辑弹窗状态
const novelDialogVisible = ref(false)
const novelEditLoading = ref(false)
const novelSaving = ref(false)
const allTemplates = ref([])       // 全部可选用模板
const novelSelectedIds = ref([])   // 弹窗中当前勾选的 ID

// 切换到本小说标签页时加载
async function switchToNovelTab() {
  activeTab.value = 'novel'
  await loadNovelSettings()
}

// 加载本小说已选设定
async function loadNovelSettings() {
  if (!store.currentNovelId) return
  try {
    const res = await projectApi.getSettings(store.currentNovelId)
    const ids = res.setting_ids || []
    // 获取这些设定的完整信息
    if (ids.length) {
      const all = await settingApi.list({ template_only: true })
      novelSettings.value = all.filter(s => ids.includes(s.id))
    } else {
      novelSettings.value = []
    }
  } catch {
    novelSettings.value = []
  }
}

// 打开编辑弹窗
async function openNovelSettingEditor() {
  if (!store.currentNovelId) return
  novelDialogVisible.value = true
  novelEditLoading.value = true
  try {
    // 并行加载：已选 ID + 全部模板
    const [settingRes, templates] = await Promise.all([
      projectApi.getSettings(store.currentNovelId),
      settingApi.templates(),
    ])
    allTemplates.value = templates
    novelSelectedIds.value = settingRes.setting_ids || []
  } catch (e) {
    ElMessage.error('加载失败：' + (e?.message || '未知错误'))
  } finally {
    novelEditLoading.value = false
  }
}

// 保存本小说设定选择
async function saveNovelSettings() {
  if (!store.currentNovelId) return
  novelSaving.value = true
  try {
    await projectApi.updateSettings(store.currentNovelId, novelSelectedIds.value)
    ElMessage.success('已更新本小说设定库')
    novelDialogVisible.value = false
    await loadNovelSettings()
  } catch (e) {
    ElMessage.error('保存失败：' + (e?.message || '未知错误'))
  } finally {
    novelSaving.value = false
  }
}

// 监听小说切换：切回全局 tab + 重置
watch(() => store.currentNovelId, () => {
  activeTab.value = hasNovel.value ? 'novel' : 'global'
  if (hasNovel.value) loadNovelSettings()
})
</script>

<style scoped>
.sv { padding: 4px; }
.sv-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  flex-wrap: wrap;
  gap: 10px;
}
.sv-title { font-size: 16px; font-weight: 600; display: flex; align-items: baseline; gap: 10px; }
.sv-sub { font-size: 13px; color: #909399; font-weight: 400; }
.sv-toolbar-actions { display: flex; gap: 10px; align-items: center; }
.sv-card { margin-bottom: 14px; }
.sv-tag { margin-right: 4px; }
.sv-hint { font-size: 12px; color: #909399; margin-top: 4px; }
.muted { color: #c0c4cc; }

/* 子标签页 */
.sv-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.sv-tab {
  padding: 8px 18px;
  cursor: pointer;
  font-size: 14px;
  color: var(--el-text-color-regular);
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}
.sv-tab:hover { color: var(--el-color-primary); }
.sv-tab-active {
  color: #ff4d4f;
  border-bottom-color: #ff4d4f;
  font-weight: 600;
}

/* 本小说设定库列表 */
.sv-novel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-weight: 500;
}
.sv-novel-list { display: flex; flex-direction: column; gap: 8px; }
.sv-novel-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 6px;
}
.sv-novel-name { font-weight: 500; min-width: 160px; }
.sv-novel-desc { color: #909399; font-size: 13px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 编辑弹窗 */
.sv-novel-edit-hint { color: #909399; font-size: 13px; margin-bottom: 10px; }
.sv-novel-edit-list { display: flex; flex-direction: column; gap: 6px; max-height: 320px; overflow-y: auto; }
.sv-novel-edit-item { width: 100%; margin: 0 !important; align-items: center; height: auto; }
.sv-novel-meta { color: #909399; font-size: 12px; margin-left: auto; }
.sv-novel-count { margin-top: 10px; text-align: right; color: #909399; font-size: 12px; }
</style>
