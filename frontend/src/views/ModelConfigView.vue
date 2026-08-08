<template>
  <div class="mc">
    <div class="mc-head">
      <div>
        <h2 class="mc-title">模型配置</h2>
        <p class="mc-sub">多厂商 API 统一网关：可视化添加模型、测试连通性、指定默认生成模型。</p>
      </div>
      <el-button type="primary" @click="openCreate">新增模型</el-button>
    </div>

    <el-table :data="list" border stripe class="mc-table">
      <el-table-column prop="name" label="名称" min-width="160" />
      <el-table-column label="厂商" width="110">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ vendorLabel(row.vendor) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="model_name" label="模型" min-width="150" />
      <el-table-column label="任务分组" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="row.role === 'primary' ? 'primary' : 'info'">{{ roleLabel(row.role) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">
            {{ row.status === 'active' ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="默认" width="70" align="center">
        <template #default="{ row }">
          <el-icon v-if="row.is_default" color="#67c23a"><CircleCheckFilled /></el-icon>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="思考" width="70" align="center">
        <template #default="{ row }">
          <el-icon v-if="row.enable_thinking" color="#409eff"><CircleCheckFilled /></el-icon>
          <span v-else class="muted">关闭</span>
        </template>
      </el-table-column>
      <el-table-column prop="api_key" label="密钥" width="120">
        <template #default="{ row }">
          <span class="muted">{{ row.api_key || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="240" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" text @click="testRow(row)">测试</el-button>
          <el-button
            size="small"
            text
            type="success"
            :disabled="row.is_default"
            @click="setDefault(row)"
          >设默认</el-button>
          <el-button size="small" text type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-alert
      v-if="!list.length"
      class="mc-empty"
      type="info"
      :closable="false"
      title="还没有配置任何模型"
      description="点击右上角「新增模型」，填入厂商 API 地址与密钥，并「设为默认」后即可在对话页生成章节。"
    />

    <!-- 新增 / 编辑 弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑模型' : '新增模型'" width="640px">
      <el-form :model="form" label-width="110px" class="mc-form">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="例如：DeepSeek · 创作主力" />
        </el-form-item>
        <el-form-item label="厂商">
          <el-select v-model="form.vendor" @change="onVendorChange" style="width: 100%">
            <el-option v-for="v in VENDORS" :key="v" :label="vendorLabel(v)" :value="v" />
          </el-select>
        </el-form-item>
        <el-form-item label="API 地址">
          <el-input v-model="form.api_base" placeholder="https://..." />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            placeholder="留空表示不修改（编辑时）"
          />
        </el-form-item>
        <el-form-item label="模型名称">
          <el-input v-model="form.model_name" placeholder="例如 deepseek-chat" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="上下文窗口">
              <el-input-number v-model="form.context_window" :min="1024" :step="1024" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最大 tokens">
              <el-input-number v-model="form.max_tokens" :min="256" :step="256" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="温度">
              <el-slider v-model="form.temperature" :min="0" :max="1" :step="0.1" show-input />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="top_p">
              <el-slider v-model="form.top_p" :min="0" :max="1" :step="0.05" show-input />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="任务分组">
              <el-select v-model="form.role" style="width: 100%">
                <el-option label="创作主力" value="primary" />
                <el-option label="记忆压缩" value="memory" />
                <el-option label="设定解析" value="parse" />
                <el-option label="伏笔推演" value="foreshadow" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态">
              <el-select v-model="form.status" style="width: 100%">
                <el-option label="启用" value="active" />
                <el-option label="停用" value="disabled" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="设为默认">
          <el-switch v-model="form.is_default" />
          <span class="mc-hint">默认模型用于「生成章节」。</span>
        </el-form-item>
        <el-form-item label="思考模式">
          <el-switch v-model="form.enable_thinking" />
          <span class="mc-hint">关闭后模型不再深度思考（更快、更省 token，适合本地 qwen3 等思考型模型）。</span>
        </el-form-item>
        <el-form-item label="备用模型">
          <el-switch v-model="form.is_backup" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button @click="testForm">测试连接</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { modelApi } from '@/api/model'

const VENDORS = ['deepseek', 'qwen', 'kimi', 'openai', 'claude', 'ollama', 'ernie', 'spark', 'custom', 'placeholder', 'siliconflow', 'nvidia', 'zhipu']

// 厂商中文标签（下拉与表格中展示）
const VENDOR_LABELS = {
  deepseek: 'DeepSeek',
  qwen: '通义千问',
  ernie: '文心一言',
  spark: '讯飞星火',
  kimi: 'Kimi(月之暗面)',
  openai: 'OpenAI',
  claude: 'Claude(Anthropic)',
  ollama: 'Ollama(本地)',
  custom: '自定义',
  placeholder: '占位(未接入)',
  siliconflow: '硅基流动',
  nvidia: '英伟达 NIM',
  zhipu: '智谱 GLM',
}

// 厂商预设：切换厂商时自动填充 API 地址与模型名（仅当用户未手填时）
const PRESETS = {
  deepseek: { api_base: 'https://api.deepseek.com/v1', model_name: 'deepseek-chat' },
  qwen: { api_base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model_name: 'qwen-plus' },
  kimi: { api_base: 'https://api.moonshot.cn/v1', model_name: 'moonshot-v1-8k' },
  openai: { api_base: 'https://api.openai.com/v1', model_name: 'gpt-4o-mini' },
  claude: { api_base: 'https://api.anthropic.com/v1', model_name: 'claude-3-5-sonnet-20241022' },
  ollama: { api_base: 'http://localhost:11434/v1', model_name: 'llama3' },
  ernie: { api_base: 'https://qianfan.baidubce.com/v2', model_name: 'ernie-4.0-8k' },
  spark: { api_base: 'https://spark-api-open.xf-yun.com/v1', model_name: 'generalv3.5' },
  siliconflow: { api_base: 'https://api.siliconflow.cn/v1', model_name: 'Qwen/Qwen2.5-72B-Instruct' },
  nvidia: { api_base: 'https://integrate.api.nvidia.com/v1', model_name: 'nvidia/llama-3.1-nemotron-70b-instruct' },
  zhipu: { api_base: 'https://open.bigmodel.cn/api/paas/v4', model_name: 'glm-4-flash' },
}

function vendorLabel(v) {
  return VENDOR_LABELS[v] || v
}

const list = ref([])
const dialogVisible = ref(false)
const editingId = ref('')
const form = reactive({
  name: '', vendor: 'deepseek', api_base: '', api_key: '', model_name: '',
  context_window: 32768, temperature: 0.4, top_p: 0.9, max_tokens: 6000,
  role: 'primary', status: 'active', is_default: false, is_backup: false,
  enable_thinking: true,
})

function roleLabel(r) {
  return { primary: '创作主力', memory: '记忆压缩', parse: '设定解析', foreshadow: '伏笔推演' }[r] || r
}

async function load() {
  try {
    const res = await modelApi.list()
    list.value = Array.isArray(res) ? res : (res.items || [])
  } catch (e) {
    console.error(e)
  }
}

function resetForm() {
  Object.assign(form, {
    name: '', vendor: 'deepseek', api_base: '', api_key: '', model_name: '',
    context_window: 32768, temperature: 0.4, top_p: 0.9, max_tokens: 6000,
    role: 'primary', status: 'active', is_default: false, is_backup: false,
    enable_thinking: true,
  })
  onVendorChange(form.vendor)
}

function openCreate() {
  editingId.value = ''
  resetForm()
  dialogVisible.value = true
}

async function openEdit(row) {
  editingId.value = row.id
  try {
    const full = await modelApi.get(row.id) // 详情返回完整密钥
    Object.assign(form, {
      name: full.name, vendor: full.vendor, api_base: full.api_base,
      api_key: full.api_key || '', model_name: full.model_name,
      context_window: full.context_window, temperature: full.temperature,
      top_p: full.top_p, max_tokens: full.max_tokens, role: full.role,
      status: full.status, is_default: full.is_default, is_backup: full.is_backup,
      enable_thinking: full.enable_thinking !== false,
    })
    dialogVisible.value = true
  } catch (e) {
    ElMessage.error('加载模型详情失败')
  }
}

function onVendorChange(v) {
  const p = PRESETS[v]
  if (!p) return
  if (!form.api_base) form.api_base = p.api_base
  if (!form.model_name) form.model_name = p.model_name
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning('请填写名称')
  if (!form.api_base.trim()) return ElMessage.warning('请填写 API 地址')
  if (!form.model_name.trim()) return ElMessage.warning('请填写模型名称')
  const payload = { ...form }
  // 编辑且密钥为「不修改」标记时，后端保留原值；此处由 api_key 是否为空判断
  try {
    if (editingId.value) {
      await modelApi.update(editingId.value, payload)
      ElMessage.success('已更新')
    } else {
      await modelApi.create(payload)
      ElMessage.success('已添加')
    }
    dialogVisible.value = false
    await load()
  } catch (e) {
    /* 错误已通过 http 拦截器提示 */
  }
}

async function testForm() {
  const payload = {
    vendor: form.vendor, api_base: form.api_base, api_key: form.api_key,
    model_name: form.model_name, model_id: editingId.value || undefined,
  }
  const loading = ElMessage.info('正在测试连接…')
  try {
    const res = await modelApi.test(payload)
    ElMessage.closeAll()
    if (res.ok) ElMessage.success(`连接成功（${res.latency_ms} ms）`)
    else ElMessage.warning(`连接失败：${res.msg}`)
  } catch (e) {
    ElMessage.closeAll()
  }
}

async function testRow(row) {
  try {
    const res = await modelApi.test({
      vendor: row.vendor, api_base: row.api_base, api_key: '',
      model_name: row.model_name, model_id: row.id,
    })
    if (res.ok) ElMessage.success(`「${row.name}」连接成功（${res.latency_ms} ms）`)
    else ElMessage.warning(`「${row.name}」连接失败：${res.msg}`)
  } catch (e) {
    /* 拦截器已提示 */
  }
}

async function setDefault(row) {
  try {
    await modelApi.setDefault(row.id)
    ElMessage.success(`已将「${row.name}」设为默认生成模型`)
    await load()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除模型「${row.name}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await modelApi.remove(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

onMounted(load)
</script>

<style scoped>
.mc { padding: 4px; }
.mc-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.mc-title { margin: 0 0 4px; }
.mc-sub { margin: 0; font-size: 13px; color: #909399; }
.mc-table { margin-top: 8px; }
.mc-empty { margin-top: 16px; }
.mc-form { padding-right: 8px; }
.mc-hint { font-size: 12px; color: #909399; margin-left: 8px; }
.muted { color: #c0c4cc; }
</style>
