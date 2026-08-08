<template>
  <div class="wm">
    <div class="wm-toolbar">
      <div class="wm-title">
        世界地图
        <span class="wm-novel">当前作品：{{ store.currentNovel?.name || '未选择' }}</span>
      </div>
      <div class="wm-actions">
        <el-tag v-if="planes.length" type="info" effect="plain">
          共 {{ planes.length }} 个位面 · {{ list.length }} 个地点
        </el-tag>
        <el-button :icon="MapLocation" @click="goLocations">去地点库</el-button>
      </div>
    </div>

    <!-- 空态：无地点数据 -->
    <el-empty
      v-if="!loading && list.length === 0"
      description="当前作品还没有地点，先在「地点库」里添加带坐标和位面的地点吧"
    >
      <el-button type="primary" :icon="Plus" @click="goLocations">去地点库添加</el-button>
    </el-empty>

    <template v-else>
      <!-- 位面切换：完全由地点库里实际出现的 plane 动态生成 -->
      <el-tabs v-model="activePlane" class="wm-plane-tabs" type="card">
        <el-tab-pane v-for="p in planes" :key="p" :name="p">
          <template #label>
            <span class="wm-plane-label">
              <el-icon><Collection /></el-icon> {{ p }}
              <el-badge :value="grouped[p].length" class="wm-plane-badge" type="primary" />
            </span>
          </template>
        </el-tab-pane>
      </el-tabs>

      <div class="wm-body" v-loading="loading">
        <div class="wm-canvas-wrap">
          <svg
            ref="svgEl"
            class="wm-svg"
            :class="{ grabbing: isDragging }"
            :viewBox="viewBoxStr"
            preserveAspectRatio="xMidYMid meet"
            @mousedown="onMouseDown"
            @mousemove="onMouseMove"
            @mouseup="onMouseUp"
            @mouseleave="onMouseUp"
            @wheel.prevent="onWheel"
            @click="onSvgBlankClick"
            @contextmenu.prevent="onSvgRightClick"
          >
            <!-- 背景：覆盖整个 viewBox，不再有任何「画布消失」的 clip 边界 -->
            <rect :x="vb.x" :y="vb.y" :width="vb.w" :height="vb.h" fill="#fbfcfe" />

            <!-- 方位罗盘：固定在 viewBox 右下角 -->
            <g class="wm-compass" :transform="`translate(${vb.x + vb.w - 44}, ${vb.y + vb.h - 44})`">
              <circle r="20" fill="#fff" stroke="#e4e7ed" />
              <text x="0" y="-11" text-anchor="middle" class="wm-compass-n">北</text>
              <text x="0" y="17" text-anchor="middle" class="wm-compass-s">南</text>
              <text x="13" y="4" text-anchor="middle" class="wm-compass-e">东</text>
              <text x="-13" y="4" text-anchor="middle" class="wm-compass-w">西</text>
            </g>

            <!-- 位面标题水印：固定在 viewBox 左下角 -->
            <text :x="vb.x + 16" :y="vb.y + vb.h - 16" class="wm-plane-watermark">{{ activePlane }}</text>

            <!-- 地图内容：可平移/缩放 -->
            <g :transform="`matrix(${view.scale},0,0,${view.scale},${view.tx},${view.ty})`">
              <!-- 背景网格：覆盖整个 viewBox，随缩放平移 -->
              <g class="wm-grid">
                <line
                  v-for="(ln, i) in gridLines"
                  :key="`g-${i}`"
                  :x1="ln.x1" :y1="ln.y1" :x2="ln.x2" :y2="ln.y2"
                  :stroke="ln.major ? '#d0d7de' : '#ebedf0'"
                  :stroke-width="ln.major ? 1.5 : 1"
                />
              </g>

              <!-- 每个地点的几何图形：单击选中、双击编辑、拖拽改坐标 -->
              <g
                v-for="loc in currentPlaneLocs"
                :key="loc.id"
                class="wm-loc"
                :class="{ 'is-dragging': draggingLocId === loc.id }"
                @mousedown.stop="onLocMouseDown($event, loc)"
                @click.stop="select(loc)"
                @dblclick.stop="openEdit(loc)"
                @contextmenu.stop.prevent="onLocRightClick(loc)"
              >
                <!-- 形状：圆形 -->
                <circle
                  v-if="loc.shape === 'circle'"
                  :cx="proj(loc).x" :cy="proj(loc).y"
                  :r="Math.max(6, (loc.radius || 10) * renderScale)"
                  class="wm-shape" :class="{ 'is-active': selectedId === loc.id }"
                />
                <!-- 形状：矩形 -->
                <rect
                  v-else-if="loc.shape === 'rect'"
                  :x="proj(loc).x - (loc.radius || 10) * renderScale"
                  :y="proj(loc).y - (loc.radius_y || 10) * renderScale"
                  :width="2 * (loc.radius || 10) * renderScale"
                  :height="2 * (loc.radius_y || 10) * renderScale"
                  class="wm-shape" :class="{ 'is-active': selectedId === loc.id }"
                />
                <!-- 形状：扇形 -->
                <path
                  v-else-if="loc.shape === 'sector'"
                  :d="sectorPath(loc)"
                  class="wm-shape" :class="{ 'is-active': selectedId === loc.id }"
                />
                <!-- 形状：多边形 -->
                <polygon
                  v-else-if="loc.shape === 'polygon' && loc.polygon"
                  :points="polygonPoints(loc)"
                  class="wm-shape" :class="{ 'is-active': selectedId === loc.id }"
                />
                <!-- 默认/点：标记圆点 -->
                <circle
                  v-else
                  :cx="proj(loc).x" :cy="proj(loc).y" :r="selectedId === loc.id ? 9 : 6"
                  class="wm-dot" :class="{ 'is-active': selectedId === loc.id }"
                />
                <!-- 名称标签 -->
                <text
                  :x="proj(loc).x" :y="proj(loc).y - (markerR(loc) + 8)"
                  text-anchor="middle" class="wm-label"
                  :class="{ 'is-active': selectedId === loc.id }"
                >{{ loc.name }}</text>
              </g>
            </g>
          </svg>

          <!-- 视图控制浮层 -->
          <div class="wm-controls">
            <el-button-group>
              <el-button :icon="ZoomIn" title="放大" @click="zoomBy(1.2)" />
              <el-button :icon="ZoomOut" title="缩小" @click="zoomBy(1 / 1.2)" />
              <el-button :icon="RefreshRight" title="重置视图" @click="resetView" />
            </el-button-group>
            <div class="wm-zoom-info">{{ Math.round(view.scale * 100) }}%</div>
          </div>

          <p class="wm-canvas-hint">
            提示：滚轮缩放，拖拽空白处平移；单击地点查看详情，双击编辑，拖动地点可直接改坐标。
            右键空白处新建地点，右键地点可编辑、丰富其内部细节。坐标为统一世界系（x 向东、y 向北）。
          </p>
        </div>

        <!-- 右侧详情面板 -->
        <div class="wm-detail" v-if="selected">
          <div class="wm-detail-head">
            <span class="wm-detail-name">{{ selected.name }}</span>
            <el-tag v-if="selected.location_type" size="small" effect="light">{{ selected.location_type }}</el-tag>
          </div>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="位面">{{ selected.plane || '未设位面' }}</el-descriptions-item>
            <el-descriptions-item label="坐标">
              {{ fmt(selected.center_x) }}, {{ fmt(selected.center_y) }}
            </el-descriptions-item>
            <el-descriptions-item label="高度">{{ selected.height != null ? selected.height : '—' }}</el-descriptions-item>
            <el-descriptions-item label="形状">{{ selected.shape || '点' }}</el-descriptions-item>
            <el-descriptions-item label="区域">{{ selected.region || '—' }}</el-descriptions-item>
          </el-descriptions>

          <div class="wm-detail-block" v-if="selected.description">
            <div class="wm-detail-sub">描述</div>
            <p class="wm-detail-text">{{ selected.description }}</p>
          </div>

          <div class="wm-detail-block" v-if="(selected.notable_features || []).length">
            <div class="wm-detail-sub">特色地标</div>
            <div class="wm-features">
              <el-tag v-for="f in selected.notable_features" :key="f" size="small" effect="plain">{{ f }}</el-tag>
            </div>
          </div>

          <!-- 同位面其他地点的方位/距离（本地坐标推导） -->
          <div class="wm-detail-block" v-if="relations.length">
            <div class="wm-detail-sub">同位面方位 / 距离</div>
            <el-table :data="relations" size="small" border stripe>
              <el-table-column prop="name" label="地点" min-width="100" />
              <el-table-column prop="bearing" label="方位" width="70" />
              <el-table-column prop="distance" label="距离" width="90" />
              <el-table-column label="高度差" width="70">
                <template #default="{ row }">{{ row.height_diff ?? '—' }}</template>
              </el-table-column>
            </el-table>
          </div>
          <div class="wm-detail-actions">
            <el-button text size="small" @click="selectedId = null">收起</el-button>
            <el-button type="primary" text size="small" :icon="Edit" @click="openEdit(selected)">编辑</el-button>
          </div>
        </div>

        <div class="wm-detail wm-detail-empty" v-else>
          <el-icon class="wm-detail-placeholder"><LocationFilled /></el-icon>
          <p>点击地图上的地点查看详情</p>
        </div>
      </div>
    </template>
  </div>

  <!-- 新建/编辑地点对话框 -->
  <el-dialog
    v-model="editorVisible"
    :title="editingId ? '编辑地点' : '新建地点'"
    width="640px"
    append-to-body
    :close-on-click-modal="false"
    @closed="onEditorClosed"
  >
    <LocationForm v-if="formModel" v-model="formModel" />
    <template #footer>
      <el-button v-if="editingId" type="danger" plain @click="onDelete">删除</el-button>
      <span class="wm-dialog-spacer" />
      <el-button @click="editorVisible = false">取消</el-button>
      <el-button type="primary" @click="onSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, MapLocation, Collection, LocationFilled,
  ZoomIn, ZoomOut, RefreshRight, Edit,
} from '@element-plus/icons-vue'
import { useProjectStore } from '@/store/project'
import { locationApi } from '@/api/database'
import LocationForm from '@/components/database/LocationForm.vue'

const router = useRouter()
const store = useProjectStore()
const projectId = computed(() => store.currentNovelId)

// 归一化目标画布（仅用于计算 baseScale，让内容初始填满一个固定大小的参考框）
const TARGET_W = 960
const TARGET_H = 640
const PAD = 44
// 不对称留白：左上方留更多空白，让内容整体偏右下，避免「挤在左上」（同时让地图尽可能铺满）
const LEFT_PAD = 168
const TOP_PAD = 112

const list = ref([])
const loading = ref(false)
const activePlane = ref('')
const selectedId = ref(null)
const svgEl = ref(null)

// 画布真实像素尺寸：viewBox 直接取元素尺寸（viewBox 单位 == CSS 像素），
// 这样 preserveAspectRatio 不再产生 letterbox 留黑边，地图充满整个画布、整体显得更大
const svgSize = reactive({ w: TARGET_W, h: TARGET_H })
let resizeObserver = null
function measureSvg() {
  const el = svgEl.value
  if (!el) return
  const r = el.getBoundingClientRect()
  if (r.width > 0 && r.height > 0) {
    svgSize.w = r.width
    svgSize.h = r.height
  }
}

// 拖拽地点改坐标：冻结包围盒，避免拖动过程中地图整体缩放导致偏移；用「抓取点偏移」精确定位
const draggingLocId = ref(null)
const dragFrozenBounds = ref(null)
const locGrab = reactive({ dx: 0, dy: 0 })
const locMoved = ref(false)

// 地点编辑器（新建/编辑）
const editorVisible = ref(false)
const editingId = ref(null)
const formModel = ref(null)

// 视图变换：scale + translate（基于 viewBox 坐标系）
const view = reactive({ scale: 1, tx: 0, ty: 0 })
const isDragging = ref(false)
const dragStart = reactive({ x: 0, y: 0, tx: 0, ty: 0 })

async function load() {
  if (!projectId.value) return
  loading.value = true
  try {
    const res = await locationApi.list(projectId.value)
    list.value = Array.isArray(res) ? res : (res.items || [])
    if (activePlane.value && !grouped.value[activePlane.value]) activePlane.value = ''
    if (!activePlane.value && planes.value.length) activePlane.value = planes.value[0]
  } catch (e) {
    ElMessage.error('加载地点失败：' + (e?.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

// 按 plane 分组（无位面的归为「未设位面」）
const grouped = computed(() => {
  const g = {}
  for (const l of list.value) {
    const k = l.plane || '未设位面'
    ;(g[k] ||= []).push(l)
  }
  return g
})

// 位面列表：保持出现顺序；「未设位面」排最后
const planes = computed(() => {
  const keys = Object.keys(grouped.value)
  return keys.sort((a, b) => {
    if (a === '未设位面') return 1
    if (b === '未设位面') return -1
    return 0
  })
})

const currentPlaneLocs = computed(() => grouped.value[activePlane.value] || [])

// 当前位面的世界坐标包围盒（含地点半径外扩，不含网格留白）
const rawBounds = computed(() => {
  const locs = currentPlaneLocs.value
  if (!locs.length) return { minX: 0, maxX: 100, minY: 0, maxY: 100 }
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (const l of locs) {
    const xs = [l.center_x ?? 0]
    const ys = [l.center_y ?? 0]
    if (l.shape === 'polygon' && Array.isArray(l.polygon)) {
      for (const [x, y] of l.polygon) { xs.push(x); ys.push(y) }
    }
    for (const x of xs) { minX = Math.min(minX, x); maxX = Math.max(maxX, x) }
    for (const y of ys) { minY = Math.min(minY, y); maxY = Math.max(maxY, y) }
  }
  // 含半径外扩，避免形状被裁切
  const maxR = Math.max(10, ...locs.map((l) => (l.radius || l.radius_y || 10)))
  minX -= maxR; maxX += maxR; minY -= maxR; maxY += maxR
  if (maxX - minX < 1) { minX -= 50; maxX += 50 }
  if (maxY - minY < 1) { minY -= 50; maxY += 50 }
  return { minX, maxX, minY, maxY }
})

// 网格步长：由真实内容跨度决定
const gridStep = computed(() => {
  const b = rawBounds.value
  return niceStep(Math.max(b.maxX - b.minX, b.maxY - b.minY))
})

// 最终包围盒：在 rawBounds 基础上再往外扩 5 个网格单元，让边界由完整格子自然组成
// 拖拽地点时冻结此包围盒，避免拖动过程中地图整体缩放
const bounds = computed(() => {
  if (dragFrozenBounds.value) return dragFrozenBounds.value
  const b = rawBounds.value
  const step = gridStep.value
  const cells = 5
  return {
    minX: Math.floor(b.minX / step) * step - cells * step,
    maxX: Math.ceil(b.maxX / step) * step + cells * step,
    minY: Math.floor(b.minY / step) * step - cells * step,
    maxY: Math.ceil(b.maxY / step) * step + cells * step,
  }
})

// 基础缩放：把世界单位映射到画布像素，让内容初始铺满「画布可用区」（左上留白更大）
const baseScale = computed(() => {
  const b = bounds.value
  const w = svgSize.w || TARGET_W
  const h = svgSize.h || TARGET_H
  const availW = Math.max(50, w - LEFT_PAD - PAD)
  const availH = Math.max(50, h - TOP_PAD - PAD)
  const sx = availW / (b.maxX - b.minX)
  const sy = availH / (b.maxY - b.minY)
  return Math.min(sx, sy)
})

// viewBox 直接等于画布元素的真实像素尺寸：viewBox 单位 == CSS 像素，
// preserveAspectRatio 不再留黑边（letterbox），地图充满整个画布、整体显得更大
const vb = computed(() => {
  const w = svgSize.w || TARGET_W
  const h = svgSize.h || TARGET_H
  return { x: 0, y: 0, w: Math.max(120, w), h: Math.max(120, h) }
})

const viewBoxStr = computed(() => `${vb.value.x} ${vb.value.y} ${vb.value.w} ${vb.value.h}`)

// 渲染时的总缩放（基础 * 视图）
const renderScale = computed(() => baseScale.value * view.scale)

// 世界坐标 → viewBox 坐标（内容已自动填满 viewBox，左/上留白更大）
function proj(loc) {
  const b = bounds.value
  const s = baseScale.value
  return {
    x: LEFT_PAD + (loc.center_x - b.minX) * s,
    y: TOP_PAD + (b.maxY - loc.center_y) * s,
  }
}

function markerR(loc) {
  if (loc.shape === 'circle') return Math.max(6, (loc.radius || 10) * renderScale.value)
  if (loc.shape === 'rect') return Math.max(6, (loc.radius || loc.radius_y || 10) * renderScale.value)
  return 6
}

function sectorPath(loc) {
  const c = proj(loc)
  const r = Math.max(6, (loc.radius || 10) * renderScale.value)
  const a0 = ((loc.angle ?? 0) - (loc.angle_span ?? 60) / 2) * Math.PI / 180
  const a1 = ((loc.angle ?? 0) + (loc.angle_span ?? 60) / 2) * Math.PI / 180
  // SVG y 向下，角度取反以匹配「北=上」
  const x0 = c.x + r * Math.sin(a0)
  const y0 = c.y - r * Math.cos(a0)
  const x1 = c.x + r * Math.sin(a1)
  const y1 = c.y - r * Math.cos(a1)
  const large = (loc.angle_span ?? 60) > 180 ? 1 : 0
  return `M ${c.x} ${c.y} L ${x0.toFixed(1)} ${y0.toFixed(1)} A ${r} ${r} 0 ${large} 1 ${x1.toFixed(1)} ${y1.toFixed(1)} Z`
}

function polygonPoints(loc) {
  if (!Array.isArray(loc.polygon)) return ''
  return loc.polygon.map(([x, y]) => {
    const p = proj({ center_x: x, center_y: y })
    return `${p.x.toFixed(1)},${p.y.toFixed(1)}`
  }).join(' ')
}

// 固定网格：严格画在内容边界内，边界本身由 contentBox 矩形描边负责，形成闭合地图框
const gridLines = computed(() => {
  const b = bounds.value
  const span = Math.max(b.maxX - b.minX, b.maxY - b.minY)
  const step = niceStep(span)
  // 只保留落在 [minX, maxX] / [minY, maxY] 内的网格线，避免在留白里出现悬浮线
  const startX = Math.ceil(b.minX / step) * step
  const endX = Math.floor(b.maxX / step) * step
  const startY = Math.ceil(b.minY / step) * step
  const endY = Math.floor(b.maxY / step) * step

  const lines = []
  const majorEvery = 5
  let idx = 0
  for (let x = startX; x <= endX + step * 0.001; x += step) {
    const p1 = proj({ center_x: x, center_y: b.minY })
    const p2 = proj({ center_x: x, center_y: b.maxY })
    const major = Math.abs(Math.round(x / step)) % majorEvery === 0
    lines.push({ x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y, major, key: idx++ })
  }
  for (let y = startY; y <= endY + step * 0.001; y += step) {
    const p1 = proj({ center_x: b.minX, center_y: y })
    const p2 = proj({ center_x: b.maxX, center_y: y })
    const major = Math.abs(Math.round(y / step)) % majorEvery === 0
    lines.push({ x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y, major, key: idx++ })
  }
  return lines
})

// 已移除单独的 contentBox 边界矩形：边界由最外圈完整网格单元自然组成

function niceStep(span) {
  if (span <= 0) return 50
  const target = 8
  const raw = span / target
  const pow = Math.pow(10, Math.floor(Math.log10(raw)))
  const n = raw / pow
  let mult = 1
  if (n >= 5) mult = 5
  else if (n >= 2) mult = 2
  else mult = 1
  return mult * pow
}

// 工具：把鼠标像素坐标转成 viewBox 坐标
// 关键：SVG 用了 preserveAspectRatio="xMidYMid meet"，元素与 viewBox 宽高比不一致时
// 浏览器会居中留黑边（letterbox）。这里必须按 meet 的真实缩放比 + 居中偏移反算，
// 否则越远离中心误差越大，拖拽地点会明显「跟不上」鼠标。
function clientToSvg(clientX, clientY) {
  const rect = svgEl.value?.getBoundingClientRect()
  if (!rect) return { x: 0, y: 0 }
  const vbw = vb.value.w
  const vbh = vb.value.h
  const scale = Math.min(rect.width / vbw, rect.height / vbh) // meet：取较小缩放比
  const offX = (rect.width - vbw * scale) / 2 // 居中留黑边产生的水平偏移
  const offY = (rect.height - vbh * scale) / 2 // 居中留黑边产生的垂直偏移
  return {
    x: (clientX - rect.left - offX) / scale,
    y: (clientY - rect.top - offY) / scale,
  }
}

// viewBox 坐标 → 世界坐标
function svgToWorld(sx, sy) {
  const b = bounds.value
  const s = baseScale.value
  return {
    x: b.minX + (sx - LEFT_PAD) / s,
    y: b.maxY - (sy - TOP_PAD) / s,
  }
}

// 屏幕坐标 → 世界坐标（考虑当前 view 变换）
function screenToWorld(clientX, clientY) {
  return screenToWorldWith(clientX, clientY, bounds.value, baseScale.value)
}

// 屏幕坐标 → 世界坐标（使用指定的 bounds/baseScale，用于拖拽地点时冻结投影）
function screenToWorldWith(clientX, clientY, b, s) {
  const p = clientToSvg(clientX, clientY)
  const nx = (p.x - view.tx) / view.scale
  const ny = (p.y - view.ty) / view.scale
  return {
    x: b.minX + (nx - LEFT_PAD) / s,
    y: b.maxY - (ny - TOP_PAD) / s,
  }
}

// 交互：拖拽空白处平移
function onMouseDown(e) {
  if (e.button !== 0) return
  isDragging.value = true
  const p = clientToSvg(e.clientX, e.clientY)
  dragStart.x = p.x
  dragStart.y = p.y
  dragStart.tx = view.tx
  dragStart.ty = view.ty
}

// 在某个地点上按下：进入「拖拽改坐标」模式（阻止冒泡，避免触发地图平移）
function onLocMouseDown(e, loc) {
  if (e.button !== 0) return
  e.stopPropagation()
  draggingLocId.value = loc.id
  locMoved.value = false
  // 冻结当前包围盒：拖动期间地图不再整体缩放，地点能精确贴合鼠标
  dragFrozenBounds.value = bounds.value
  // 记录抓取点相对地点中心的偏移，拖动全程保持该偏移，避免「跳一下」
  const w = screenToWorld(e.clientX, e.clientY)
  locGrab.dx = w.x - (loc.center_x ?? 0)
  locGrab.dy = w.y - (loc.center_y ?? 0)
}

function onMouseMove(e) {
  // 优先处理「拖拽地点改坐标」
  if (draggingLocId.value) {
    const loc = list.value.find((l) => l.id === draggingLocId.value)
    if (loc) {
      // 用冻结包围盒把鼠标像素坐标反算成世界坐标，再减去抓取偏移得到新中心
      const w = screenToWorld(e.clientX, e.clientY)
      const nx = w.x - locGrab.dx
      const ny = w.y - locGrab.dy
      loc.center_x = Math.round(nx * 100) / 100
      loc.center_y = Math.round(ny * 100) / 100
      locMoved.value = true
    }
    return
  }
  if (!isDragging.value) return
  const p = clientToSvg(e.clientX, e.clientY)
  view.tx = dragStart.tx + (p.x - dragStart.x)
  view.ty = dragStart.ty + (p.y - dragStart.y)
}

async function onMouseUp() {
  // 结束「拖拽地点改坐标」：若有移动则保存到后端
  if (draggingLocId.value) {
    const id = draggingLocId.value
    const loc = list.value.find((l) => l.id === id)
    draggingLocId.value = null
    dragFrozenBounds.value = null
    if (locMoved.value && loc) {
      try {
        await locationApi.update(projectId.value, id, {
          name: loc.name,
          location_type: loc.location_type,
          plane: loc.plane,
          region: loc.region,
          description: loc.description,
          center_x: loc.center_x,
          center_y: loc.center_y,
          height: loc.height,
          shape: loc.shape,
          radius: loc.radius,
          radius_y: loc.radius_y,
          angle: loc.angle,
          angle_span: loc.angle_span,
          polygon: loc.polygon,
          notable_features: loc.notable_features || [],
        })
        selectedId.value = id
      } catch (e) {
        ElMessage.error('移动保存失败，已还原')
        await load()
      }
    }
    locMoved.value = false
    return
  }
  isDragging.value = false
}

// 交互：滚轮缩放（以鼠标指针为锚点，使用 viewBox 坐标）
function onWheel(e) {
  const p = clientToSvg(e.clientX, e.clientY)
  const scaleFactor = e.deltaY < 0 ? 1.15 : 1 / 1.15
  zoomAt(p.x, p.y, scaleFactor)
}

function zoomAt(svgX, svgY, factor) {
  const newScale = Math.min(Math.max(view.scale * factor, 0.2), 5)
  const ratio = newScale / view.scale
  view.tx = svgX - (svgX - view.tx) * ratio
  view.ty = svgY - (svgY - view.ty) * ratio
  view.scale = newScale
}

function zoomBy(factor) {
  zoomAt(vb.value.x + vb.value.w / 2, vb.value.y + vb.value.h / 2, factor)
}

function resetView() {
  view.scale = 1
  view.tx = 0
  view.ty = 0
}

const selected = computed(() => currentPlaneLocs.value.find((l) => l.id === selectedId.value) || null)

// 同位面其他地点的方位/距离（本地坐标推导，与后端 geo-relations 口径一致）
const relations = computed(() => {
  const s = selected.value
  if (!s || s.center_x == null || s.center_y == null) return []
  const out = []
  for (const o of currentPlaneLocs.value) {
    if (o.id === s.id || o.center_x == null || o.center_y == null) continue
    const dx = o.center_x - s.center_x
    const dy = o.center_y - s.center_y
    const dist = Math.sqrt(dx * dx + dy * dy)
    // 方位：0=北，顺时针；atan2(dx, dy) 因 y 向北
    let deg = Math.atan2(dx, dy) * 180 / Math.PI
    if (deg < 0) deg += 360
    const bearing = compass(deg)
    out.push({
      name: o.name,
      distance: Math.round(dist * 10) / 10,
      bearing,
      height_diff: (o.height != null && s.height != null) ? Math.round((o.height - s.height) * 10) / 10 : null,
    })
  }
  return out.sort((a, b) => a.distance - b.distance)
})

function compass(deg) {
  const dirs = ['北', '东北', '东', '东南', '南', '西南', '西', '西北']
  return dirs[Math.round(deg / 45) % 8]
}

function fmt(v) {
  return v == null ? '—' : (typeof v === 'number' ? v : v)
}

function select(loc) { selectedId.value = loc.id }

// 点击空白处：取消选中（新建统一用右键，避免误建）
function onSvgBlankClick(e) {
  const moved = Math.hypot(e.clientX - dragStart.x, e.clientY - dragStart.y)
  if (moved > 4) return
  selectedId.value = null
}

// 右键空白处新建：以该处世界坐标为中心
function onSvgRightClick(e) {
  const w = screenToWorld(e.clientX, e.clientY)
  openCreate(w.x, w.y)
}

// 右键地点：打开编辑，丰富其内部细节（描述 / 特色地标等）
function onLocRightClick(loc) {
  openEdit(loc)
}

function emptyForm(x, y) {
  return {
    name: '',
    location_type: '',
    plane: (activePlane.value && activePlane.value !== '未设位面') ? activePlane.value : '',
    region: '',
    description: '',
    center_x: Math.round(x * 100) / 100,
    center_y: Math.round(y * 100) / 100,
    height: 0,
    shape: 'point',
    radius: 10,
    radius_y: 10,
    angle: 0,
    angle_span: 60,
    polygon: null,
    notable_features: [],
  }
}

function openCreate(x, y) {
  editingId.value = null
  formModel.value = emptyForm(x, y)
  editorVisible.value = true
}

function openEdit(loc) {
  if (!loc) return
  editingId.value = loc.id
  formModel.value = JSON.parse(JSON.stringify({
    name: loc.name,
    location_type: loc.location_type,
    plane: loc.plane,
    region: loc.region,
    description: loc.description,
    center_x: loc.center_x,
    center_y: loc.center_y,
    height: loc.height,
    shape: loc.shape,
    radius: loc.radius,
    radius_y: loc.radius_y,
    angle: loc.angle,
    angle_span: loc.angle_span,
    polygon: loc.polygon,
    notable_features: loc.notable_features || [],
  }))
  editorVisible.value = true
}

async function onSave() {
  if (!formModel.value || !formModel.value.name || !formModel.value.name.trim()) {
    ElMessage.warning('请填写地点名称')
    return
  }
  try {
    if (editingId.value) {
      const updated = await locationApi.update(projectId.value, editingId.value, formModel.value)
      await load()
      selectedId.value = updated.id
      ElMessage.success('已保存')
    } else {
      const created = await locationApi.create(projectId.value, formModel.value)
      await load()
      selectedId.value = created.id
      ElMessage.success('已创建')
    }
    editorVisible.value = false
  } catch (e) {
    // 拦截器已提示
  }
}

async function onDelete() {
  if (!editingId.value) return
  try {
    await ElMessageBox.confirm('确定删除该地点？此操作不可撤销。', '删除确认', {
      type: 'warning',
    })
  } catch (e) {
    return
  }
  try {
    await locationApi.remove(projectId.value, editingId.value)
    await load()
    selectedId.value = null
    editorVisible.value = false
    ElMessage.success('已删除')
  } catch (e) {
    // 拦截器已提示
  }
}

function onEditorClosed() {
  formModel.value = null
  editingId.value = null
}

function goLocations() { router.push({ name: 'location' }) }

onMounted(() => {
  measureSvg()
  if (typeof ResizeObserver !== 'undefined' && svgEl.value) {
    resizeObserver = new ResizeObserver(measureSvg)
    resizeObserver.observe(svgEl.value)
  }
  load()
})
onBeforeUnmount(() => {
  if (resizeObserver) resizeObserver.disconnect()
})
watch(projectId, load)
watch(planes, (p) => {
  if (!activePlane.value && p.length) activePlane.value = p[0]
})
// 切换位面时重置视图
watch(activePlane, resetView)
</script>

<style scoped>
/* 让世界地图页占满整个视口可用高度，禁止页面级纵向滚动 */
.wm {
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
  padding: 0 8px 8px;
  overflow: hidden;
}
.wm > .el-empty { flex: 1; overflow: hidden; }
.wm-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; flex: 0 0 auto; }
.wm-title { font-size: 18px; font-weight: 600; }
.wm-novel { font-size: 13px; font-weight: 400; color: #909399; margin-left: 10px; }
.wm-actions { display: flex; align-items: center; gap: 10px; }
.wm-plane-tabs { margin-bottom: 6px; flex: 0 0 auto; }
.wm-plane-label { display: inline-flex; align-items: center; gap: 4px; }
.wm-plane-badge { margin-left: 4px; }
.wm-body { position: relative; flex: 1; min-height: 0; display: flex; }
.wm-canvas-wrap { position: relative; flex: 1; min-height: 0; height: 100%; background: transparent; border: none; border-radius: 0; padding: 0; }
.wm-svg { width: 100%; height: 100%; display: block; background: #fbfcfe; border-radius: 8px; cursor: grab; user-select: none; box-shadow: inset 0 0 0 1px var(--el-border-color-lighter); }
.wm-svg.grabbing { cursor: grabbing; }
.wm-svg:active { cursor: grabbing; }
.wm-compass text { font-size: 11px; fill: #909399; }
.wm-compass { pointer-events: none; }
.wm-plane-watermark { font-size: 13px; fill: #c0c4cc; font-weight: 600; pointer-events: none; }
.wm-grid { pointer-events: none; }
.wm-loc { cursor: pointer; }
.wm-loc.is-dragging { cursor: grabbing; }
.wm-shape { fill: rgba(64,158,255,0.18); stroke: #409eff; stroke-width: 1.5; cursor: pointer; transition: fill .15s; }
.wm-shape.is-active { fill: rgba(230,162,60,0.28); stroke: #e6a23c; }
.wm-dot { fill: #409eff; stroke: #fff; stroke-width: 2; cursor: pointer; }
.wm-dot.is-active { fill: #e6a23c; r: 9; }
.wm-label { font-size: 12px; fill: #303133; cursor: pointer; paint-order: stroke; stroke: #fff; stroke-width: 3px; }
.wm-label.is-active { fill: #e6a23c; font-weight: 600; }
.wm-canvas-hint { position: absolute; left: 16px; bottom: 12px; margin: 0; font-size: 12px; color: #909399; pointer-events: none; background: rgba(255,255,255,0.85); padding: 2px 8px; border-radius: 4px; }

.wm-controls {
  position: absolute;
  top: 12px;
  left: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  z-index: 10;
  padding: 4px;
  background: rgba(255,255,255,0.92);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.wm-controls :deep(.el-button) {
  padding: 6px 8px;
  font-size: 14px;
}
.wm-zoom-info {
  font-size: 11px;
  color: #606266;
  min-width: 34px;
  text-align: center;
}

.wm-detail { position: absolute; top: 16px; right: 16px; width: 320px; max-height: calc(100% - 32px); overflow: auto; background: rgba(255,255,255,0.96); border: 1px solid var(--el-border-color-light); border-radius: 8px; padding: 14px; box-shadow: 0 4px 16px rgba(0,0,0,0.08); z-index: 5; }
.wm-detail-empty { position: absolute; top: 16px; right: 16px; width: 220px; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #c0c4cc; background: rgba(255,255,255,0.9); border: 1px solid var(--el-border-color-light); border-radius: 8px; padding: 16px; z-index: 5; }
.wm-detail-placeholder { font-size: 48px; margin-bottom: 8px; }
.wm-detail-head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.wm-detail-name { font-size: 16px; font-weight: 600; }
.wm-detail-block { margin-top: 12px; }
.wm-detail-sub { font-size: 13px; font-weight: 600; color: #606266; margin-bottom: 6px; }
.wm-detail-text { margin: 0; font-size: 13px; color: #606266; line-height: 1.6; white-space: pre-wrap; }
.wm-features { display: flex; flex-wrap: wrap; gap: 6px; }
.wm-detail-close { margin-top: 12px; padding-left: 0; }
.wm-detail-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; padding-top: 8px; border-top: 1px solid var(--el-border-color-lighter); }
.wm-dialog-spacer { flex: 1; }
</style>
