// SVG 视口变换 composable —— 统一「拖拽平移 + 滚轮缩放 + 坐标换算」（Phase 3.3，2026-09-10）。
//
// 改造前 `WorldMapView.vue` 与 `CharacterRelationView.vue` 各手写了一份
// `view{scale,tx,ty}` + `clientToSvg` + `zoomAt` + `zoomBy` + `resetView`，
// 数值常量（缩放步进 1.15、范围 0.2~5）与换算公式完全一致，只有变量名不同。
//
// ⚠️ 关键约束：两个视图都用 `preserveAspectRatio="xMidYMid meet"`，即元素与 viewBox
// 宽高比不一致时会居中留黑边。`clientToSvg` 必须把这段黑边偏移减掉，否则缩放锚点
// 与鼠标位置会系统性偏移（图越大越明显）。这段"meet 偏移"计算是本 composable 的
// 核心价值——曾经两个视图都各自踩过这个坑。

import { computed, reactive, ref } from 'vue'

/** 滚轮/按钮的缩放步进与上下限（两视图保持一致，勿单独改） */
export const ZOOM_STEP = 1.15
export const ZOOM_MIN = 0.2
export const ZOOM_MAX = 5

/**
 * @param {() => {x:number,y:number,w:number,h:number}} getViewBox
 *   取当前 viewBox 的 getter（通常是 computed 的 `.value`）。
 * @param {{svgRef?: import('vue').Ref<SVGSVGElement|null>, onDragEnd?: () => void}} [opts]
 *   `svgRef`：SVG 元素引用（用于 getBoundingClientRect）；
 *   `onDragEnd`：平移结束时回调（部分视图需在此复位游标状态）。
 */
export function useSvgViewport(getViewBox, { svgRef, onDragEnd } = {}) {
  /** 视图变换：scale + translate（基于 viewBox 坐标系） */
  const view = reactive({ scale: 1, tx: 0, ty: 0 })

  /** 是否正在拖拽平移（供 UI 切 grabbing 光标） */
  const isDragging = ref(false)

  /** 拖拽起点快照（viewBox 坐标 + 当时的平移量） */
  const dragStart = reactive({ x: 0, y: 0, tx: 0, ty: 0 })

  /**
   * 屏幕像素坐标 → viewBox 坐标。
   * 处理 `preserveAspectRatio="xMidYMid meet"` 的居中留黑边偏移。
   */
  function clientToSvg(clientX, clientY) {
    const rect = svgRef?.value?.getBoundingClientRect()
    if (!rect) return { x: 0, y: 0 }
    const { w: vbw, h: vbh } = getViewBox()
    // meet：取较小缩放比，短边方向会产生留白
    const scale = Math.min(rect.width / vbw, rect.height / vbh)
    const offX = (rect.width - vbw * scale) / 2
    const offY = (rect.height - vbh * scale) / 2
    return {
      x: (clientX - rect.left - offX) / scale,
      y: (clientY - rect.top - offY) / scale,
    }
  }

  /** 屏幕像素坐标 → 内容（世界/图）坐标：先转 viewBox 再去掉视图变换 */
  function screenToContent(clientX, clientY) {
    const p = clientToSvg(clientX, clientY)
    return { x: (p.x - view.tx) / view.scale, y: (p.y - view.ty) / view.scale }
  }

  /** 以给定 viewBox 坐标点为锚点缩放（锚点不动，周围内容随之放大/缩小） */
  function zoomAt(svgX, svgY, factor) {
    const newScale = Math.min(Math.max(view.scale * factor, ZOOM_MIN), ZOOM_MAX)
    const ratio = newScale / view.scale
    view.tx = svgX - (svgX - view.tx) * ratio
    view.ty = svgY - (svgY - view.ty) * ratio
    view.scale = newScale
  }

  /** 以 viewBox 中心为锚点缩放（工具条按钮用） */
  function zoomBy(factor) {
    const vb = getViewBox()
    zoomAt(vb.x + vb.w / 2, vb.y + vb.h / 2, factor)
  }

  function resetView() {
    view.scale = 1
    view.tx = 0
    view.ty = 0
  }

  // ---- 拖拽平移 ----
  function startPan(e) {
    if (e.button !== 0) return
    isDragging.value = true
    const p = clientToSvg(e.clientX, e.clientY)
    dragStart.x = p.x
    dragStart.y = p.y
    dragStart.tx = view.tx
    dragStart.ty = view.ty
  }

  /** @returns {boolean} 是否消费了本次移动（调用方可据此提前 return） */
  function movePan(e) {
    if (!isDragging.value) return false
    const p = clientToSvg(e.clientX, e.clientY)
    view.tx = dragStart.tx + (p.x - dragStart.x)
    view.ty = dragStart.ty + (p.y - dragStart.y)
    return true
  }

  function endPan() {
    if (!isDragging.value) return
    isDragging.value = false
    onDragEnd?.()
  }

  /** 滚轮处理：以指针为锚点缩放（模板里用 `@wheel.prevent="onWheel"`） */
  function onWheel(e) {
    const p = clientToSvg(e.clientX, e.clientY)
    const factor = e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP
    zoomAt(p.x, p.y, factor)
  }

  /** 内容层 transform：`matrix(scale,0,0,scale,tx,ty)` */
  const contentTransform = computed(
    () => `matrix(${view.scale},0,0,${view.scale},${view.tx},${view.ty})`
  )

  /** 缩放百分比（显示用，如 120） */
  const zoomPercent = computed(() => Math.round(view.scale * 100))

  return {
    view,
    isDragging,
    dragStart,
    clientToSvg,
    screenToContent,
    zoomAt,
    zoomBy,
    resetView,
    startPan,
    movePan,
    endPan,
    onWheel,
    contentTransform,
    zoomPercent,
  }
}
