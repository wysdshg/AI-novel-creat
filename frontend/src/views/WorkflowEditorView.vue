<template>
  <div class="wfed">
    <!-- ================= 顶栏 ================= -->
    <div class="wfed-toolbar">
      <el-button text :icon="ArrowLeft" @click="$router.push('/workspace/workflow')">返回</el-button>
      <el-input v-model="form.name" class="wfed-name" placeholder="工作流名称" maxlength="120" />
      <el-tooltip content="保存画布" placement="bottom">
        <el-button :icon="Check" circle @click="save" :loading="saving" />
      </el-tooltip>
      <el-button type="primary" :icon="VideoPlay" :loading="running" @click="openRun">运行</el-button>
      <el-button :icon="Clock" @click="openHistory">历史</el-button>
      <span class="wfed-status" :class="'s-' + globalStatus">{{ statusText }}</span>
    </div>

    <!-- ================= 主体三栏 ================= -->
    <div class="wfed-main">
      <!-- 左侧：节点面板 -->
      <aside class="wfed-palette">
        <div class="palette-title">节点</div>
        <div v-for="(group, cat) in palette" :key="cat" class="palette-group">
          <div class="palette-cat">{{ cat }}</div>
          <div
            v-for="m in group"
            :key="m.type"
            class="palette-item"
            draggable="true"
            @dragstart="onDragStart($event, m.type)"
            @dblclick="addNode(m.type, { x: 80 + Math.random() * 300, y: 80 + Math.random() * 200 })"
          >
            <span class="palette-icon" :class="`pi-${m.type}`">{{ iconOf(m.type) }}</span>
            <div class="palette-text">
              <div class="palette-name">{{ m.label }}</div>
              <div class="palette-desc">{{ m.description }}</div>
            </div>
          </div>
        </div>
        <div class="palette-tip">拖拽到画布或双击添加</div>
      </aside>

      <!-- 中间：画布 -->
      <section class="wfed-canvas" @dragover.prevent @drop="onDrop">
        <VueFlow
          v-model:nodes="nodes"
          v-model:edges="edges"
          :node-types="nodeTypes"
          :min-zoom="0.2"
          :max-zoom="2"
          fit-view-on-init
          @connect="onConnect"
          @node-click="onNodeClick"
          @pane-click="onPaneClick"
          @edge-click="onEdgeClick"
        >
          <Background :gap="16" :variant="BackgroundVariant.Dots" />
          <Controls position="bottom-left" />
          <MiniMap pannable zoomable position="bottom-right" />
          <Panel v-if="!nodes.length" position="top-center" class="wfed-empty">
            从左侧拖拽节点到这里，双击「开始」创建入口
          </Panel>
        </VueFlow>
      </section>

      <!-- 右侧：属性面板 -->
      <aside class="wfed-props" v-show="showProps">
        <template v-if="selectedEdge">
          <div class="props-title">边属性</div>
          <div class="props-route">{{ selectedEdge.source }} → {{ selectedEdge.target }}</div>
          <div class="field">
            <label>条件</label>
            <el-select v-model="edgeCondition" style="width: 100%" @change="onEdgeConditionChange">
              <el-option label="总是执行 (always)" value="always" />
              <el-option label="上游成功 (success)" value="success" />
              <el-option label="上游失败 (failure)" value="failure" />
              <el-option label="分支为真 (if_else:true)" value="if_else:true" />
              <el-option label="分支为假 (if_else:false)" value="if_else:false" />
            </el-select>
          </div>
        </template>

        <template v-else-if="selectedNode">
          <div class="props-title">
            {{ nodeMeta?.label || '节点' }}
            <el-button text size="small" type="danger" @click="removeSelected">删除</el-button>
          </div>
          <div class="field">
            <label>显示名</label>
            <el-input v-model="selectedNode.data.label" placeholder="节点显示名" maxlength="60" />
          </div>
          <template v-for="f in nodeMeta?.params_schema || []" :key="f.name">
            <div class="field">
              <label>{{ f.label }}</label>

              <!-- string -->
              <el-input
                v-if="f.type === 'string'"
                v-model="selParams[f.name]"
                :placeholder="f.placeholder"
                clearable
              />

              <!-- number -->
              <el-input-number
                v-else-if="f.type === 'number'"
                v-model="selParams[f.name]"
                :controls="false"
                style="width: 100%"
              />

              <!-- boolean -->
              <el-switch v-else-if="f.type === 'boolean'" v-model="selParams[f.name]" />

              <!-- select -->
              <el-select v-else-if="f.type === 'select'" v-model="selParams[f.name]" style="width: 100%">
                <el-option v-for="opt in f.options" :key="opt" :label="opt" :value="opt" />
              </el-select>

              <!-- textarea -->
              <el-input
                v-else-if="f.type === 'textarea'"
                v-model="selParams[f.name]"
                type="textarea"
                :rows="4"
                :placeholder="f.placeholder"
              />

              <!-- variable -->
              <template v-else-if="f.type === 'variable'">
                <el-input v-model="selParams[f.name]" :placeholder="f.placeholder || '如 start_1.title'" clearable />
                <div class="field-help">可选节点：{{ nodeIdList.join(' / ') }}</div>
              </template>

              <!-- 结构化 multifield：高频字段用表格，其余用 JSON -->
              <template v-else-if="f.type === 'multifield'">
                <div v-if="isTableField(f)" class="multi-table">
                  <div v-for="(row, ri) in (selParams[f.name] || [])" :key="ri" class="multi-row">
                    <template v-for="col in tableCols(f, row)" :key="col.key">
                      <el-input
                        v-if="col.kind === 'input'"
                        v-model="row[col.key]"
                        :placeholder="col.ph"
                        size="small"
                      />
                      <el-select v-else-if="col.kind === 'select'" v-model="row[col.key]" size="small">
                        <el-option v-for="opt in col.options" :key="opt" :label="opt" :value="opt" />
                      </el-select>
                      <el-switch v-else-if="col.kind === 'switch'" v-model="row[col.key]" size="small" />
                    </template>
                    <el-button text size="small" type="danger" @click="delRow(f.name, ri)">删</el-button>
                  </div>
                  <el-button size="small" style="width: 100%" @click="addRow(f.name)">+ 添加一行</el-button>
                </div>
                <template v-else>
                  <el-input
                    :model-value="multiText[f.name]"
                    type="textarea"
                    :rows="5"
                    :placeholder="f.help"
                    @input="(v) => onMultiInput(f.name, v)"
                  />
                  <div v-if="multiErr[f.name]" class="multi-err">{{ multiErr[f.name] }}</div>
                </template>
              </template>

              <div v-if="f.help && f.type !== 'multifield' && !isTableField(f)" class="field-help">{{ f.help }}</div>
            </div>
          </template>

          <div class="props-outputs" v-if="nodeMeta?.outputs && Object.keys(nodeMeta.outputs).length">
            <div class="props-title sub">输出变量</div>
            <div v-for="(desc, name) in nodeMeta.outputs" :key="name" class="out-item">
              <code>{{ name }}</code> — <span>{{ desc }}</span>
            </div>
          </div>
        </template>

        <div v-else class="props-none">
          <p>点击节点编辑参数</p>
          <p>点击连线设置条件</p>
        </div>
      </aside>
    </div>

    <!-- ================= 运行参数弹窗 ================= -->
    <el-dialog v-model="runDialog" title="运行参数" width="420px" top="12vh">
      <div class="run-vars">
        <div v-for="v in startVariables" :key="v.name" class="field">
          <label>{{ v.label || v.name }}<span v-if="v.required" class="req">*</span></label>
          <el-input-number
            v-if="v.type === 'number'"
            v-model="runForm[v.name]"
            :controls="false"
            style="width: 100%"
          />
          <el-select v-else-if="v.type === 'select'" v-model="runForm[v.name]" style="width: 100%">
            <el-option v-for="opt in v.options || []" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <el-input v-else v-model="runForm[v.name]" :placeholder="v.type === 'number' ? '数字' : '文本'" />
        </div>
        <div v-if="!startVariables.length" class="muted">该工作流没有输入变量，直接运行</div>
      </div>
      <template #footer>
        <el-button @click="runDialog = false">取消</el-button>
        <el-button type="primary" :loading="running" @click="confirmRun">开始运行</el-button>
      </template>
    </el-dialog>

    <!-- ================= 运行结果弹窗 ================= -->
    <el-dialog v-model="resultDialog" title="运行结果" width="560px" top="8vh">
      <el-alert
        v-if="runResult"
        :type="runResult.status === 'success' ? 'success' : 'error'"
        :title="runResult.status === 'success' ? '运行成功' : '运行失败'"
        :description="runResult.error || `耗时 ${runResult.duration_ms} ms`"
        :closable="false"
        show-icon
        style="margin-bottom: 10px"
      />
      <div class="result-box">
        <pre>{{ prettyOutputs }}</pre>
      </div>
    </el-dialog>

    <!-- ================= 运行历史弹窗 ================= -->
    <el-dialog v-model="historyDialog" title="运行历史" width="720px" top="8vh">
      <el-table :data="historyList" v-loading="historyLoading" size="small" max-height="420">
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : 'info'" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.started_at) }}</template>
        </el-table-column>
        <el-table-column prop="duration_ms" label="耗时(ms)" width="90" />
        <el-table-column label="输入" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ strOf(row.inputs) }}</template>
        </el-table-column>
        <el-table-column label="输出" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ strOf(row.outputs) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="showRunDetail(row.id)">轨迹</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 轨迹详情 -->
      <div v-if="runDetail" class="run-detail">
        <div class="props-title sub">节点轨迹（{{ runDetail.run.status }}）</div>
        <div v-for="nr in runDetail.node_runs" :key="nr.node_id" class="trace-row">
          <el-tag :type="traceTag(nr.status)" size="small" effect="plain">{{ nr.status }}</el-tag>
          <span class="trace-label">{{ nr.label || nr.node_id }}</span>
          <span class="trace-ms">{{ nr.duration_ms ?? '-' }} ms</span>
          <el-popover width="360" trigger="click">
            <template #reference>
              <el-button size="small" text type="primary">详情</el-button>
            </template>
            <div class="trace-pop">
              <div class="tp-title">输入</div>
              <pre>{{ strOf(nr.inputs) }}</pre>
              <div class="tp-title">输出</div>
              <pre>{{ strOf(nr.outputs) }}</pre>
              <div v-if="nr.error" class="tp-title err">错误</div>
              <pre v-if="nr.error" class="err">{{ nr.error }}</pre>
            </div>
          </el-popover>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  VueFlow, useVueFlow, Panel,
} from '@vue-flow/core'
import { Background, BackgroundVariant } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'
import { ArrowLeft, Check, VideoPlay, Clock } from '@element-plus/icons-vue'
import { workflowApi, workflowRunStream } from '@/api/workflow'
import WorkflowNode from '@/components/workflow/WorkflowNode.vue'

const route = useRoute()
const router = useRouter()
const wfId = route.params.id

// ---------- vue-flow store ----------
const store = useVueFlow({ id: 'wf-editor' })
const { addNodes, addEdges, screenToFlowCoordinate } = store
const nodes = ref([])
const edges = ref([])
const nodeTypes = {
  start: WorkflowNode, end: WorkflowNode, llm: WorkflowNode,
  'setting-retrieval': WorkflowNode, 'if-else': WorkflowNode,
  code: WorkflowNode, template: WorkflowNode, chapter: WorkflowNode,
}

// ---------- 表单 ----------
const form = reactive({ name: '', description: '', tags: [], is_active: true })
const editingId = ref(wfId === 'new' ? null : wfId)
const saving = ref(false)

// ---------- 节点元数据（后端 meta） ----------
const nodeTypesMeta = ref([])
const palette = computed(() => {
  const groups = {}
  for (const m of nodeTypesMeta.value) {
    (groups[m.category] ||= []).push(m)
  }
  return groups
})
const ICONS = {
  start: '始', end: '止', llm: 'AI', 'setting-retrieval': '设',
  'if-else': '分', code: '码', template: '模', chapter: '章',
}
const iconOf = (t) => ICONS[t] || '？'

// ---------- 选择 ----------
const selectedNode = ref(null)
const selectedEdge = ref(null)
const showProps = computed(() => !!(selectedNode.value || selectedEdge.value))
const nodeMeta = computed(() => {
  if (!selectedNode.value) return null
  return nodeTypesMeta.value.find((m) => m.type === selectedNode.value.data.nodeType) || null
})
const selParams = computed(() => {
  if (!selectedNode.value) return {}
  return selectedNode.value.data.params || (selectedNode.value.data.params = {})
})
const nodeIdList = computed(() => nodes.value.map((n) => n.id))

// multifield JSON 编辑（非表格字段）
const multiText = reactive({})
const multiErr = reactive({})
function onMultiInput(name, v) {
  try {
    selParams.value[name] = v.trim() ? JSON.parse(v) : []
    multiErr[name] = ''
  } catch {
    multiErr[name] = 'JSON 格式错误（检查逗号/引号）'
  }
}

// 表格渲染的 multifield 字段
const TABLE_FIELDS = {
  start: { variables: ['name', 'label', 'type'] },
  end: { outputs: ['name', 'selector'] },
  'if-else': { conditions: ['selector', 'operator', 'value'] },
}
const isTableField = (f) => {
  const t = selectedNode.value?.data.nodeType
  return !!TABLE_FIELDS[t]?.[f.name]
}
function tableCols(f, row) {
  const t = selectedNode.value?.data.nodeType
  const cfg = {
    start: { variables: [
      { key: 'name', kind: 'input', ph: '变量名(如 title)' },
      { key: 'label', kind: 'input', ph: '显示名' },
      { key: 'type', kind: 'select', options: ['string', 'number', 'select'] },
    ] },
    end: { outputs: [
      { key: 'name', kind: 'input', ph: '输出名(如 result)' },
      { key: 'selector', kind: 'input', ph: '如 llm_1.text' },
    ] },
    'if-else': { conditions: [
      { key: 'selector', kind: 'input', ph: '如 start_1.score' },
      { key: 'operator', kind: 'select', options: ['contains', 'not_contains', 'eq', 'ne', 'gt', 'ge', 'lt', 'le', 'empty', 'not_empty', 'start_with', 'end_with'] },
      { key: 'value', kind: 'input', ph: '比较值' },
    ] },
  }
  return cfg[t]?.[f.name] || []
}
function addRow(fname) {
  const t = selectedNode.value?.data.nodeType
  const defaults = {
    start: { variables: { name: '', label: '', type: 'string', required: false, default: null } },
    end: { outputs: { name: '', selector: '' } },
    'if-else': { conditions: { selector: '', operator: 'eq', value: '' } },
  }
  const d = defaults[t]?.[fname] || {}
  if (!Array.isArray(selParams.value[fname])) selParams.value[fname] = []
  selParams.value[fname].push({ ...d })
}
function delRow(fname, i) {
  selParams.value[fname].splice(i, 1)
}

// ---------- 画布交互 ----------
let counter = 1000
function onDragStart(evt, type) {
  evt.dataTransfer.setData('application/vueflow', type)
  evt.dataTransfer.effectAllowed = 'move'
}
function onDrop(evt) {
  const type = evt.dataTransfer.getData('application/vueflow')
  if (!type) return
  const pos = screenToFlowCoordinate({ x: evt.clientX, y: evt.clientY })
  addNode(type, pos)
}
function addNode(type, position) {
  const id = `${type}_${++counter}`
  const meta = nodeTypesMeta.value.find((m) => m.type === type)
  const params = {}
  for (const f of meta?.params_schema || []) {
    if (f.default !== undefined) params[f.name] = f.default
    else if (f.type === 'boolean') params[f.name] = false
    else if (f.type === 'multifield') params[f.name] = []
    else if (f.type === 'number') params[f.name] = null
    else params[f.name] = ''
  }
  addNodes([{
    id,
    type,
    position,
    data: { label: '', nodeType: type, params, status: 'idle' },
  }])
  // 新节点自动选中
  const node = nodes.value.find((n) => n.id === id)
  if (node) selectNode(node)
}
function onConnect(conn) {
  const src = nodes.value.find((n) => n.id === conn.source)
  let condition = 'always'
  if (src?.data?.nodeType === 'if-else') {
    const hasTrue = edges.value.some(
      (e) => e.source === conn.source && (e.data?.condition === 'if_else:true')
    )
    condition = hasTrue ? 'if_else:false' : 'if_else:true'
  }
  edges.value.push({
    id: `edge_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
    source: conn.source,
    target: conn.target,
    data: { condition },
    label: condShort(condition),
    type: condition.startsWith('if_else') ? 'smoothstep' : 'default',
  })
}
function condShort(c) {
  return { always: '', success: '成功', failure: '失败', if_else: '真', if_else_false: '假' }[c] ||
    (c === 'if_else:true' ? '真' : c === 'if_else:false' ? '假' : c || '')
}
function selectNode(node) {
  selectedNode.value = node
  selectedEdge.value = null
  // 初始化 multi JSON 文本
  for (const f of nodeMeta.value?.params_schema || []) {
    if (f.type === 'multifield' && !isTableField(f)) {
      multiText[f.name] = JSON.stringify(node.data.params?.[f.name] || [], null, 2)
      multiErr[f.name] = ''
    }
  }
}
function onNodeClick({ node }) {
  selectNode(node)
}
function onPaneClick() {
  selectedNode.value = null
  selectedEdge.value = null
}
function onEdgeClick({ edge }) {
  selectedEdge.value = edge
  selectedNode.value = null
  edgeCondition.value = edge.data?.condition || 'always'
}
const edgeCondition = ref('always')
function onEdgeConditionChange(v) {
  if (selectedEdge.value) {
    selectedEdge.value.data.condition = v
    selectedEdge.value.label = condShort(v)
  }
}
function removeSelected() {
  if (selectedNode.value) {
    const id = selectedNode.value.id
    nodes.value = nodes.value.filter((n) => n.id !== id)
    edges.value = edges.value.filter((e) => e.source !== id && e.target !== id)
    selectedNode.value = null
  }
}

// ---------- 加载 / 保存 ----------
async function load() {
  if (editingId.value) {
    const wf = await workflowApi.get(editingId.value)
    form.name = wf.name
    form.description = wf.description || ''
    form.tags = wf.tags || []
    form.is_active = wf.is_active
    for (const n of wf.nodes || []) {
      addNodes([{
        id: n.id,
        type: n.type,
        position: n.position || { x: 60, y: 60 },
        data: { label: n.label || '', nodeType: n.type, params: n.params || {}, status: 'idle' },
      }])
    }
    for (const e of wf.edges || []) {
      const c = e.condition || 'always'
      edges.value.push({
        id: e.id || `edge_${e.from}_${e.to}`,
        source: e.from,
        target: e.to,
        data: { condition: c },
        label: condShort(c),
      })
    }
    nextTick(() => store.fitView({ padding: 0.3 }))
  } else {
    form.name = '未命名工作流'
    // 新工作流自动放一个 start + end
    addNode('start', { x: 60, y: 180 })
    nextTick(() => {
      addNode('end', { x: 560, y: 180 })
      store.fitView({ padding: 0.4 })
    })
  }
}
async function save() {
  if (!form.name?.trim()) {
    ElMessage.warning('请填写名称')
    return false
  }
  const startCount = nodes.value.filter((n) => n.data.nodeType === 'start').length
  const endCount = nodes.value.filter((n) => n.data.nodeType === 'end').length
  if (startCount !== 1) { ElMessage.warning('必须有且只有一个「开始」节点'); return false }
  if (endCount !== 1) { ElMessage.warning('必须有且只有一个「结束」节点'); return false }
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      description: form.description,
      tags: form.tags,
      is_active: form.is_active,
      nodes: nodes.value.map((n) => ({
        id: n.id,
        type: n.data.nodeType,
        label: n.data.label || '',
        params: n.data.params || {},
        position: n.position || { x: 0, y: 0 },
      })),
      edges: edges.value.map((e) => ({
        id: e.id,
        from: e.source,
        to: e.target,
        condition: e.data?.condition || 'always',
      })),
    }
    if (editingId.value) {
      await workflowApi.update(editingId.value, payload)
    } else {
      const created = await workflowApi.create(payload)
      editingId.value = created.id
      router.replace(`/workspace/workflow-editor/${created.id}`)
    }
    ElMessage.success('已保存')
    return true
  } finally {
    saving.value = false
  }
}

// ---------- 运行 ----------
const running = ref(false)
const runDialog = ref(false)
const runForm = reactive({})
const startVariables = computed(() => {
  const s = nodes.value.find((n) => n.data.nodeType === 'start')
  return (s?.data?.params?.variables) || []
})
const runResult = ref(null)
const resultDialog = ref(false)
const prettyOutputs = computed(() => JSON.stringify(runResult.value?.outputs || {}, null, 2))

function openRun() {
  // 重置运行表单
  Object.keys(runForm).forEach((k) => delete runForm[k])
  if (startVariables.value.length) runDialog.value = true
  else confirmRun()
}
async function confirmRun() {
  const inputs = {}
  for (const v of startVariables.value) {
    if (runForm[v.name] !== undefined && runForm[v.name] !== '') inputs[v.name] = runForm[v.name]
  }
  runDialog.value = false
  await doRun(inputs)
}
async function doRun(inputs) {
  const ok = await save()
  if (!ok || !editingId.value) return
  running.value = true
  globalStatus.value = 'running'
  // 清空状态
  nodes.value.forEach((n) => { n.data.status = 'idle' })
  let runId = null
  try {
    await workflowRunStream(editingId.value, inputs, (evt, payload) => {
      if (evt === 'node_start') setStatus(payload.node_id, 'running')
      else if (evt === 'node_end') {
        setStatus(payload.node_id, payload.status === 'success' ? 'success' : 'failed')
      } else if (evt === 'run_end') {
        runId = payload.run_id
        runResult.value = payload
      } else if (evt === 'error') {
        ElMessage.error(payload.message || '运行出错')
        globalStatus.value = 'failed'
      }
    })
    // 用完整轨迹补 skipped 标记
    if (runId) {
      try {
        const detail = await workflowApi.runDetail(runId)
        const map = {}
        for (const nr of detail.node_runs) map[nr.node_id] = nr.status
        nodes.value.forEach((n) => {
          if (map[n.id]) n.data.status = map[n.id]
        })
      } catch { /* 轨迹补全失败不影响主流程 */ }
    }
    globalStatus.value = runResult.value?.status === 'success' ? 'success' : 'failed'
    if (runResult.value?.status === 'success') ElMessage.success('运行完成')
  } catch (e) {
    globalStatus.value = 'failed'
    ElMessage.error(e.message || '运行失败')
  } finally {
    running.value = false
  }
}
function setStatus(nodeId, status) {
  const n = nodes.value.find((x) => x.id === nodeId)
  if (n) n.data.status = status
}

// ---------- 全局状态提示 ----------
const globalStatus = ref('idle')
const statusText = computed(() => ({
  idle: '', running: '运行中…', success: '运行成功', failed: '运行失败',
}[globalStatus.value] || ''))

// ---------- 运行历史 ----------
const historyDialog = ref(false)
const historyList = ref([])
const historyLoading = ref(false)
const runDetail = ref(null)
async function openHistory() {
  historyDialog.value = true
  runDetail.value = null
  if (!editingId.value) return
  historyLoading.value = true
  try {
    historyList.value = await workflowApi.runs(editingId.value)
  } finally {
    historyLoading.value = false
  }
}
async function showRunDetail(runId) {
  runDetail.value = await workflowApi.runDetail(runId)
}
const traceTag = (s) => ({ success: 'success', failed: 'danger', running: 'warning', skipped: 'info' }[s] || 'info')
const strOf = (v) => {
  if (v === null || v === undefined) return '—'
  const s = typeof v === 'string' ? v : JSON.stringify(v)
  return s.length > 120 ? s.slice(0, 120) + '…' : s
}
const fmtTime = (t) => (t ? String(t).replace('T', ' ').slice(0, 19) : '—')

onMounted(async () => {
  const metaRes = await workflowApi.nodeTypes()
  nodeTypesMeta.value = metaRes.nodes || []
  await load()
})
</script>

<style scoped>
.wfed { display: flex; flex-direction: column; height: calc(100vh - 8px); }
.wfed-toolbar {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px; border-bottom: 1px solid #e4e7ed;
  background: #fff;
}
.wfed-name { width: 260px; }
.wfed-status { margin-left: auto; font-size: 13px; color: #909399; }
.wfed-status.s-running { color: #409eff; font-weight: 600; }
.wfed-status.s-success { color: #67c23a; font-weight: 600; }
.wfed-status.s-failed { color: #f56c6c; font-weight: 600; }

.wfed-main { flex: 1; display: flex; min-height: 0; }

/* 左侧节点面板 */
.wfed-palette {
  width: 220px; border-right: 1px solid #e4e7ed; background: #fafafa;
  overflow-y: auto; padding: 10px; flex-shrink: 0;
}
.palette-title { font-weight: 700; font-size: 14px; margin-bottom: 10px; }
.palette-cat { font-size: 12px; color: #909399; margin: 10px 0 6px; }
.palette-item {
  display: flex; align-items: center; gap: 8px; padding: 7px 8px;
  border: 1px solid #e4e7ed; border-radius: 8px; background: #fff;
  margin-bottom: 6px; cursor: grab; transition: box-shadow 0.15s, border-color 0.15s;
}
.palette-item:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-color: #c0c4cc; }
.palette-item:active { cursor: grabbing; }
.palette-icon {
  width: 26px; height: 26px; border-radius: 6px; color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; flex-shrink: 0;
}
.pi-start, .pi-end { background: #409eff; }
.pi-llm, .pi-setting-retrieval { background: #8b5cf6; }
.pi-if-else { background: #e6a23c; }
.pi-code, .pi-template { background: #67c23a; }
.pi-chapter { background: #f56c6c; }
.palette-text { min-width: 0; }
.palette-name { font-size: 13px; font-weight: 600; color: #303133; }
.palette-desc {
  font-size: 11px; color: #909399; margin-top: 2px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.palette-tip { font-size: 11px; color: #c0c4cc; text-align: center; margin-top: 12px; }

/* 中间画布 */
.wfed-canvas { flex: 1; min-width: 0; position: relative; background: #f8fafc; }
.wfed-empty { color: #909399; background: rgba(255,255,255,0.85); padding: 8px 16px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }

/* 右侧属性面板 */
.wfed-props {
  width: 280px; border-left: 1px solid #e4e7ed; background: #fff;
  overflow-y: auto; padding: 12px; flex-shrink: 0;
}
.props-title { font-weight: 700; font-size: 14px; margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between; }
.props-title.sub { font-size: 13px; margin: 14px 0 8px; color: #606266; }
.props-route { font-size: 12px; color: #909399; margin-bottom: 12px; background: #f5f7fa; border-radius: 6px; padding: 6px 8px; }
.field { margin-bottom: 12px; }
.field label { display: block; font-size: 12px; color: #606266; margin-bottom: 4px; }
.field .req { color: #f56c6c; }
.field-help { font-size: 11px; color: #909399; margin-top: 4px; line-height: 1.5; }
.multi-err { color: #f56c6c; font-size: 11px; margin-top: 4px; }
.multi-row { display: flex; gap: 4px; margin-bottom: 4px; align-items: center; }
.multi-row .el-input, .multi-row .el-select { flex: 1; }
.props-none { color: #c0c4cc; text-align: center; padding-top: 60px; font-size: 13px; line-height: 2; }
.props-outputs { border-top: 1px dashed #e4e7ed; margin-top: 8px; padding-top: 6px; }
.out-item { font-size: 12px; color: #606266; margin-bottom: 5px; }
.out-item code { background: #f5f7fa; border-radius: 4px; padding: 1px 5px; color: #8b5cf6; }

/* 运行相关 */
.run-vars .field { margin-bottom: 14px; }
.muted { color: #c0c4cc; font-size: 13px; }
.result-box { background: #0f172a; color: #e2e8f0; border-radius: 8px; padding: 12px; max-height: 320px; overflow: auto; }
.result-box pre { margin: 0; font-size: 12px; white-space: pre-wrap; word-break: break-all; }
.run-detail { border-top: 1px solid #e4e7ed; margin-top: 14px; padding-top: 10px; }
.trace-row { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px dashed #f0f2f5; font-size: 13px; }
.trace-label { flex: 1; color: #303133; }
.trace-ms { color: #909399; font-size: 12px; }
.trace-pop .tp-title { font-size: 12px; font-weight: 600; color: #606266; margin: 6px 0 2px; }
.trace-pop .tp-title.err { color: #f56c6c; }
.trace-pop pre { margin: 0; font-size: 11px; white-space: pre-wrap; word-break: break-all; background: #f5f7fa; padding: 6px; border-radius: 6px; max-height: 160px; overflow: auto; }
.trace-pop pre.err { color: #f56c6c; }
</style>
