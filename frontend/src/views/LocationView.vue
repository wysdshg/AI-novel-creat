<template>
  <div class="db">
    <div class="db-toolbar">
      <div class="db-title">
        资料库 · 地点库
        <span class="db-novel">当前作品：{{ store.currentNovel?.name || '未选择' }}</span>
      </div>
      <div class="db-toolbar-actions">
        <el-button :icon="MapLocation" @click="goMap">世界地图</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建地点</el-button>
      </div>
    </div>

    <el-card shadow="never" class="db-card">
      <el-table :data="list" v-loading="loading" empty-text="暂无地点，点击右上角新建" border stripe>
        <el-table-column prop="name" label="名称" width="160" fixed />
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.location_type" size="small" effect="light">{{ row.location_type }}</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="位面" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.plane" size="small" effect="plain" type="warning">{{ row.plane }}</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="坐标(X,Y)" width="130">
          <template #default="{ row }">
            <span v-if="row.center_x != null && row.center_y != null">{{ row.center_x }}, {{ row.center_y }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="高度" width="90">
          <template #default="{ row }">{{ row.height != null ? row.height : '—' }}</template>
        </el-table-column>
        <el-table-column label="形状" width="90">
          <template #default="{ row }">
            <span v-if="row.shape">{{ row.shape }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="region" label="所属区域" width="140">
          <template #default="{ row }">{{ row.region || '—' }}</template>
        </el-table-column>
        <el-table-column label="特色地标" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ (row.notable_features || []).join('、') || '—' }}</template>
        </el-table-column>
        <el-table-column label="描述" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" text @click="openGeo(row)">地理</el-button>
            <el-button size="small" text type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑地点' : '新建地点'"
      width="680px"
      top="6vh"
      @closed="resetForm"
    >
      <LocationForm v-model="form" />
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="geoVisible"
      title="地理关系（同位面方位 / 距离）"
      width="560px"
      top="8vh"
    >
      <div v-loading="geoLoading">
        <p v-if="geoData" class="geo-meta">
          位面：<b>{{ geoData.plane || '未设置' }}</b> · 基准地点：{{ geoData.origin?.name }}
        </p>
        <el-table :data="geoData?.relations || []" empty-text="同位面暂无其他带坐标的地点" border stripe>
          <el-table-column prop="name" label="地点" min-width="140" />
          <el-table-column prop="bearing" label="方位" width="90" />
          <el-table-column prop="distance" label="距离" width="110" />
          <el-table-column label="高度差" width="90">
            <template #default="{ row }">{{ row.height_diff ?? '—' }}</template>
          </el-table-column>
        </el-table>
        <p class="geo-hint">方位/距离由坐标自动推导（x 向东、y 向北）；跨位面地点需通过「通道」关系连接。</p>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, MapLocation } from '@element-plus/icons-vue'
import { useProjectStore } from '@/store/project'
import { locationApi } from '@/api/database'
import { useRouter } from 'vue-router'
import LocationForm from '@/components/database/LocationForm.vue'

const store = useProjectStore()
const router = useRouter()
const projectId = computed(() => store.currentNovelId)

function goMap() { router.push({ name: 'world-map' }) }

const list = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)

const emptyForm = () => ({
  name: '', location_type: null, region: '', description: '', notable_features: [],
  plane: null, center_x: null, center_y: null, shape: null,
  radius: null, radius_y: null, angle: null, angle_span: null, height: null, polygon: null,
})
const form = reactive(emptyForm())

async function load() {
  if (!projectId.value) return
  loading.value = true
  try {
    const res = await locationApi.list(projectId.value)
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
    location_type: row.location_type,
    region: row.region,
    description: row.description,
    notable_features: row.notable_features ? [...row.notable_features] : [],
    plane: row.plane ?? null,
    center_x: row.center_x ?? null,
    center_y: row.center_y ?? null,
    shape: row.shape ?? null,
    radius: row.radius ?? null,
    radius_y: row.radius_y ?? null,
    angle: row.angle ?? null,
    angle_span: row.angle_span ?? null,
    height: row.height ?? null,
    polygon: row.polygon ? JSON.parse(JSON.stringify(row.polygon)) : null,
  })
  editingId.value = row.id
  dialogVisible.value = true
}

const geoVisible = ref(false)
const geoLoading = ref(false)
const geoData = ref(null)

async function openGeo(row) {
  geoVisible.value = true
  geoLoading.value = true
  geoData.value = null
  try {
    const res = await locationApi.geoRelations(projectId.value, row.id)
    geoData.value = res
  } catch (e) {
    console.error(e)
  } finally {
    geoLoading.value = false
  }
}

async function save() {
  if (!form.name || !form.name.trim()) {
    ElMessage.warning('请填写地点名称')
    return
  }
  const payload = { ...form }
  if (editingId.value) {
    await locationApi.update(projectId.value, editingId.value, payload)
    ElMessage.success('已更新')
  } else {
    await locationApi.create(projectId.value, payload)
    ElMessage.success('已创建')
  }
  dialogVisible.value = false
  load()
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除地点「${row.name}」？`, '删除确认', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
    await locationApi.remove(projectId.value, row.id)
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
.db-toolbar-actions { display: flex; gap: 10px; }
.db-title { font-size: 18px; font-weight: 600; }
.db-novel { font-size: 13px; font-weight: 400; color: #909399; margin-left: 10px; }
.muted { color: #c0c4cc; }
.geo-meta { margin: 0 0 12px; font-size: 13px; color: #606266; }
.geo-hint { margin: 12px 0 0; font-size: 12px; color: #909399; }
</style>
