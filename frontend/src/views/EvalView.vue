<template>
  <div class="eval-page">
    <div class="ev-head">
      <h2 class="ev-title">生成评估</h2>
      <p class="ev-sub">
        每次生成章节会自动留档一个「版本」（配置快照 + 正文 + 自动指标）。
        给版本打 1~5 分，就能看出哪套配置真的更好 —— 而不是凭感觉。
      </p>
    </div>

    <div class="ev-bar">
      <el-select
        v-model="chapterId"
        placeholder="选择要评估的章节"
        filterable
        style="width: 340px"
        @change="loadAll"
      >
        <el-option v-for="c in chapterOptions" :key="c.id" :label="c.label" :value="c.id" />
      </el-select>

      <template v-if="summary">
        <span class="ev-stat">共 <b>{{ summary.total }}</b> 个版本</span>
        <span class="ev-stat">已评 <b>{{ summary.scored_count }}</b></span>
        <span class="ev-stat">均分 <b>{{ summary.avg_score ?? '—' }}</b></span>
      </template>
    </div>

    <el-empty v-if="!chapterOptions.length" description="当前作品还没有章节" />
    <el-empty v-else-if="!chapterId" description="选择一个章节，查看它的生成版本" />
    <el-empty
      v-else-if="!variants.length"
      description="该章还没有生成记录（生成一次章节后会自动留档）"
    />

    <div v-else v-loading="loading" class="ev-list">
      <div
        v-for="v in variants"
        :key="v.id"
        class="ev-card"
        :class="{ 'is-best': summary?.best?.id === v.id }"
      >
        <div class="ev-row">
          <span class="ev-time">{{ fmtTime(v.created_at) }}</span>
          <el-tag v-if="summary?.best?.id === v.id" type="success" size="small" effect="plain">
            最高分
          </el-tag>
        </div>

        <div class="ev-row ev-cfg">
          <span class="ev-chip">{{ v.config_snapshot?.model_name || '未记录模型' }}</span>
          <span class="ev-chip">温度 {{ fmtNum(v.config_snapshot?.temperature) }}</span>
          <span class="ev-chip">摄取 {{ v.config_snapshot?.ingest_level || 'full' }}</span>
          <span class="ev-chip">参考 {{ v.config_snapshot?.ref_mode || '—' }}</span>
          <span class="ev-chip">{{ v.word_count }} 字</span>
          <span class="ev-chip">{{ fmtSec(v.metrics?.duration_ms) }}</span>
          <span v-if="v.metrics?.humanize_score != null" class="ev-chip">
            去AI味 {{ v.metrics.humanize_score }}
          </span>
        </div>

        <div class="ev-row ev-score">
          <span class="ev-label">打分</span>
          <el-rate :model-value="v.score || 0" :max="5" @change="(n) => onScore(v, n)" />
          <el-input
            v-model="v._comment"
            size="small"
            placeholder="备注（可选）：哪里好 / 哪里退步"
            style="width: 300px"
            @change="() => onScore(v, v.score)"
          />
          <el-button size="small" text @click="toggleContent(v)">
            {{ v._open ? '收起正文' : '看正文' }}
          </el-button>
          <el-button size="small" text type="danger" @click="removeVariant(v)">删除</el-button>
        </div>

        <pre v-if="v._open" class="ev-content">{{ v._content || '加载中…' }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useProjectStore } from '@/store/project'
import { evalApi } from '@/api/eval'

const store = useProjectStore()
const projectId = computed(() => store.currentNovelId)

const chapterId = ref('')
const variants = ref([])
const summary = ref(null)
const loading = ref(false)

// 章节选项：复用 store.structure（与侧栏同一数据源，不额外发请求）
const chapterOptions = computed(() => {
  const out = []
  for (const vol of store.structure.volumes || []) {
    for (const art of vol.articles || []) {
      for (const ch of art.chapters || []) {
        out.push({
          id: ch.id,
          label: `${vol.name} / ${art.name} / ${ch.title || '第' + ch.chapter_no + '章'}`,
        })
      }
    }
  }
  return out
})

function fmtTime(s) {
  if (!s) return '—'
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return s
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

const fmtNum = (v) => (v === null || v === undefined ? '—' : v)
const fmtSec = (ms) => (ms ? `${(ms / 1000).toFixed(1)}s` : '—')

async function loadAll() {
  if (!projectId.value || !chapterId.value) {
    variants.value = []
    summary.value = null
    return
  }
  loading.value = true
  try {
    const [list, cmp] = await Promise.all([
      evalApi.listVariants(projectId.value, chapterId.value),
      evalApi.compare(projectId.value, chapterId.value),
    ])
    variants.value = (list || []).map((x) => ({
      ...x,
      _comment: x.comment || '',
      _open: false,
      _content: '',
    }))
    summary.value = cmp || null
  } catch (e) {
    ElMessage.error('加载版本失败')
  } finally {
    loading.value = false
  }
}

async function onScore(v, n) {
  if (!n) return
  try {
    await evalApi.score(v.id, { score: n, comment: v._comment || null })
    v.score = n
    // 分数变化会影响均分与最高分 → 重新拉一次对比数据（数据量小，直接重载最稳）
    summary.value = await evalApi.compare(projectId.value, chapterId.value)
    ElMessage.success(`已记录 ${n} 分`)
  } catch (e) {
    ElMessage.error('打分失败')
  }
}

async function toggleContent(v) {
  v._open = !v._open
  if (v._open && !v._content) {
    try {
      const d = await evalApi.getVariant(v.id)
      v._content = d?.content || '（正文为空）'
    } catch (e) {
      v._content = '（加载失败）'
    }
  }
}

async function removeVariant(v) {
  try {
    await ElMessageBox.confirm('删除这个版本？该版本的评分也会一并删除。', '确认', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await evalApi.remove(v.id)
    ElMessage.success('已删除')
    await loadAll()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

// 切换作品时重置选择（structure 会随作品变化，旧 chapterId 可能已失效）
watch(projectId, () => {
  chapterId.value = ''
  variants.value = []
  summary.value = null
})

onMounted(async () => {
  if (projectId.value && !store.structureLoaded) {
    await store.loadStructure()
  }
  // 默认选中第一章，省掉一次手动选择
  if (chapterOptions.value.length && !chapterId.value) {
    chapterId.value = chapterOptions.value[0].id
    await loadAll()
  }
})
</script>

<style scoped>
.eval-page {
  padding: 16px 20px;
}
.ev-head {
  margin-bottom: 12px;
}
.ev-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 4px;
}
.ev-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 0;
  line-height: 1.6;
}
.ev-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.ev-stat {
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.ev-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ev-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px 14px;
  background: var(--el-bg-color);
}
.ev-card.is-best {
  border-color: var(--el-color-success-light-5);
  background: var(--el-color-success-light-9);
}
.ev-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.ev-row + .ev-row {
  margin-top: 8px;
}
.ev-time {
  font-size: 13px;
  font-weight: 500;
}
.ev-cfg .ev-chip {
  font-size: 12px;
  padding: 1px 8px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
}
.ev-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.ev-content {
  margin: 10px 0 0;
  padding: 10px;
  max-height: 340px;
  overflow: auto;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
}
</style>
