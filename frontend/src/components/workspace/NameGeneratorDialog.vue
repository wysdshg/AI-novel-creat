<template>
  <el-dialog
    :model-value="modelValue"
    title="快速起名"
    width="640px"
    top="6vh"
    :close-on-click-modal="true"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <div class="ng-desc">
      纯本地随机生成（零 token、瞬时），契合「宋式小盛世」基调。结果可复制，或直接存入当前小说的设定库。
    </div>

    <!-- 控制条 -->
    <div class="ng-ctrl">
      <el-radio-group v-model="activeType" size="small">
        <el-radio-button v-for="t in NAME_TYPES" :key="t" :value="t">{{ t }}</el-radio-button>
      </el-radio-group>

      <span class="ng-ctrl-spacer" />

      <span v-show="activeType === '角色'" class="ng-ctrl-label">固定姓氏</span>
      <el-input
        v-show="activeType === '角色'"
        v-model="fixedSurname"
        size="small"
        placeholder="留空则随机"
        clearable
        :disabled="activeType !== '角色'"
        style="width: 110px"
      />

      <span v-show="activeType === '角色'" class="ng-ctrl-label">字数</span>
      <el-select v-show="activeType === '角色'" v-model="lenMode" size="small" style="width: 95px">
        <el-option label="随机" value="random" />
        <el-option label="单字" value="single" />
        <el-option label="二字" value="double" />
        <el-option label="三字" value="triple" />
      </el-select>

      <span class="ng-ctrl-label">风格</span>
      <el-select v-model="style" size="small" style="width: 110px">
        <el-option v-for="s in NAME_STYLES" :key="s" :label="s" :value="s" />
      </el-select>

      <span class="ng-ctrl-label">数量</span>
      <el-input-number v-model="count" :min="1" :max="30" size="small" controls-position="right" style="width: 100px" />

      <el-button type="primary" size="small" @click="onGenerate">生成</el-button>
    </div>

    <div v-if="activeType === '角色'" class="ng-surname-tip">
      固定姓氏仅对角色有效；留空则从常见姓氏（王李刘张等）中随机，复姓/稀有姓概率较低。
    </div>

    <!-- 结果区 -->
    <div v-if="results.length" class="ng-result">
      <div class="ng-result-head">
        <span class="ng-result-title">{{ activeType }} · 共 {{ results.length }} 个</span>
        <div class="ng-result-ops">
          <el-button size="small" text @click="copyAll">复制全部</el-button>
          <el-button
            size="small"
            text
            type="success"
            :disabled="!canSave"
            @click="saveAll"
          >全部存入</el-button>
        </div>
      </div>

      <el-alert
        v-if="!canSave"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 10px"
        title="尚未选择小说"
        description="复制可用；存入请先在左侧选择一本小说。"
      />

      <ul class="ng-list">
        <li v-for="(item, i) in results" :key="i" class="ng-item" :class="{ 'is-saved': item.saved }">
          <span class="ng-name">{{ item.name }}</span>
          <span class="ng-item-ops">
            <el-tag v-if="item.saved" type="success" size="small" effect="plain">已存入</el-tag>
            <template v-else>
              <el-button size="small" text @click="copyOne(item)">复制</el-button>
              <el-button
                size="small"
                text
                type="success"
                :disabled="!canSave"
                :loading="item.saving"
                @click="saveOne(item)"
              >存入</el-button>
            </template>
          </span>
        </li>
      </ul>
    </div>

    <el-empty v-else description="点「生成」产出候选名字" :image-size="90" />
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { genNames, NAME_TYPES, NAME_STYLES } from '@/utils/nameGen'
import { characterApi, factionApi, locationApi } from '@/api/database'
import { useProjectStore } from '@/store/project'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  projectId: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const store = useProjectStore()

const activeType = ref('角色')
const style = ref('雅致')
const count = ref(8)
const fixedSurname = ref('')
const lenMode = ref('random')
const results = ref([])

// 有效 projectId：优先父组件传入，否则取当前选中小说。
const projectId = computed(() => props.projectId || store.currentNovelId || '')
const canSave = computed(() => !!projectId.value)

// 打开弹窗时复位结果，避免上一次残留。
watch(
  () => props.modelValue,
  (open) => {
    if (open) results.value = []
  },
)

function onGenerate() {
  results.value = genNames(activeType.value, count.value, style.value, fixedSurname.value, lenMode.value).map((name) => ({
    name,
    saved: false,
    saving: false,
  }))
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

async function copyOne(item) {
  const ok = await copyText(item.name)
  if (ok) ElMessage.success(`已复制：${item.name}`)
  else ElMessage.warning('复制失败，请手动选择')
}

async function copyAll() {
  const text = results.value.map((r) => r.name).join('、')
  const ok = await copyText(text)
  if (ok) ElMessage.success(`已复制 ${results.value.length} 个名字`)
  else ElMessage.warning('复制失败，请手动选择')
}

function apiFor(type) {
  if (type === '角色') return characterApi
  if (type === '地点') return locationApi
  return factionApi
}

async function saveOne(item) {
  if (!canSave.value) return ElMessage.warning('请先选择一本小说')
  item.saving = true
  try {
    await apiFor(activeType.value).create(projectId.value, { name: item.name })
    item.saved = true
    ElMessage.success(`已存入${activeType.value}：${item.name}`)
    // 刷新侧栏树，让新实体出现在对应分类下。
    store.loadStructure(projectId.value).catch(() => {})
  } catch (e) {
    ElMessage.error('存入失败：' + (e?.response?.data?.message || e?.message || e))
  } finally {
    item.saving = false
  }
}

async function saveAll() {
  if (!canSave.value) return ElMessage.warning('请先选择一本小说')
  const pending = results.value.filter((r) => !r.saved)
  if (!pending.length) return ElMessage.info('已全部存入')
  let okCount = 0
  let fail = 0
  for (const item of pending) {
    item.saving = true
    try {
      await apiFor(activeType.value).create(projectId.value, { name: item.name })
      item.saved = true
      okCount++
    } catch {
      fail++
    } finally {
      item.saving = false
    }
  }
  if (okCount) store.loadStructure(projectId.value).catch(() => {})
  if (fail) ElMessage.warning(`${okCount} 个已存入，${fail} 个失败`)
  else ElMessage.success(`已全部存入（${okCount} 个）`)
}
</script>

<style scoped>
.ng-desc {
  font-size: 13px;
  color: #909399;
  margin-bottom: 12px;
}
.ng-ctrl {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.ng-ctrl-spacer { flex: 1; }
.ng-ctrl-label { font-size: 13px; color: #606266; }
.ng-surname-tip {
  font-size: 12px;
  color: #909399;
  margin: -8px 0 14px;
}

.ng-result-head {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}
.ng-result-title { font-size: 13px; color: #303133; font-weight: 600; }
.ng-result-ops { margin-left: auto; display: flex; gap: 4px; }

.ng-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 52vh;
  overflow-y: auto;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}
.ng-item {
  display: flex;
  align-items: center;
  padding: 9px 14px;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.ng-item:last-child { border-bottom: none; }
.ng-item.is-saved { background: #f7fbf7; }
.ng-name {
  font-size: 15px;
  color: #303133;
  letter-spacing: 1px;
  font-weight: 500;
}
.ng-item-ops { margin-left: auto; display: flex; align-items: center; gap: 6px; }
</style>
