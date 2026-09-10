<template>
  <div class="wf">
    <div class="wf-toolbar">
      <div class="wf-title">
        工作流
        <span class="wf-sub">可视化 DAG 模板 · 用工作流编排小说生成流程</span>
      </div>
      <div class="wf-toolbar-actions">
        <el-input
          v-model="keyword"
          placeholder="搜索：名称 / 描述 / 标签"
          clearable
          style="width: 240px"
          @input="load"
          @clear="load"
        />
        <el-checkbox v-model="activeOnly" @change="load">仅启用</el-checkbox>
        <el-button type="primary" :icon="Plus" @click="createAndOpen">新建工作流</el-button>
      </div>
    </div>

    <el-card shadow="never" class="wf-card">
      <el-table :data="list" v-loading="loading" empty-text="还没有工作流，点右上角新建一个吧" border stripe>
        <el-table-column prop="name" label="名称" min-width="160" fixed>
          <template #default="{ row }">
            <el-link type="primary" :underline="false" @click="openEditor(row.id)">{{ row.name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="节点 / 边" width="130">
          <template #default="{ row }">
            {{ (row.nodes || []).length }} 节点 · {{ (row.edges || []).length }} 边
          </template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.is_active" type="success" size="small" effect="plain">是</el-tag>
            <el-tag v-else type="info" size="small" effect="plain">否</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标签" min-width="150">
          <template #default="{ row }">
            <el-tag
              v-for="t in (row.tags || []).slice(0, 4)"
              :key="t"
              size="small"
              effect="plain"
              class="wf-tag"
            >{{ t }}</el-tag>
            <span v-if="!row.tags || !row.tags.length" class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain @click="openEditor(row.id)">画布编辑</el-button>
            <el-button size="small" text @click="duplicate(row)">复制</el-button>
            <el-button size="small" text :type="row.is_active ? 'warning' : 'success'" @click="toggle(row)">
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
            <el-button size="small" text type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 操作指引 -->
    <el-card shadow="never" class="wf-guide">
      <div class="guide-title">💡 用工作流生成小说：三步</div>
      <ol class="guide-list">
        <li><b>新建工作流</b>进入画布：从左侧拖入节点，把它们连起来（「开始」→ 设定检索/大模型/章节生成 → 「结束」）。</li>
        <li><b>配置节点</b>：点节点在右侧填参数，提示词里用 <code v-pre>{{#start_1.变量名#}}</code> 引用上游输出。</li>
        <li><b>运行</b>：填输入变量后点「运行」，实时看每个节点状态与输出；「历史」里可回看节点轨迹。</li>
      </ol>
      <div class="guide-note">典型流程：开始(书名/章号) → 设定检索 → 大模型(起草大纲) → 条件分支 → 章节生成(落库) → 结束</div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { workflowApi } from '@/api/workflow'

const router = useRouter()
const keyword = ref('')
const activeOnly = ref(false)
const list = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    list.value = await workflowApi.list({
      keyword: keyword.value,
      active_only: activeOnly.value,
    })
  } finally {
    loading.value = false
  }
}

function openEditor(id) {
  router.push(`/workspace/workflow-editor/${id}`)
}

async function createAndOpen() {
  const created = await workflowApi.create({
    name: '未命名工作流',
    description: '',
    tags: [],
    is_active: true,
    nodes: [],
    edges: [],
  })
  ElMessage.success('已创建，开始编排吧')
  openEditor(created.id)
}

async function duplicate(row) {
  await workflowApi.duplicate(row.id)
  ElMessage.success('已复制')
  load()
}

async function toggle(row) {
  await workflowApi.update(row.id, { is_active: !row.is_active })
  ElMessage.success(row.is_active ? '已停用' : '已启用')
  load()
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除工作流「${row.name}」？此操作不可撤销。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch { return }
  await workflowApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>

<style scoped>
.wf { padding: 4px; }
.wf-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  flex-wrap: wrap;
  gap: 10px;
}
.wf-title { font-size: 16px; font-weight: 600; display: flex; align-items: baseline; gap: 10px; }
.wf-sub { font-size: 13px; color: #909399; font-weight: 400; }
.wf-toolbar-actions { display: flex; gap: 10px; align-items: center; }
.wf-card { margin-bottom: 14px; }
.wf-tag { margin-right: 4px; }
.muted { color: #c0c4cc; }
.wf-guide { background: #f8fafc; }
.guide-title { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.guide-list { margin: 0; padding-left: 20px; line-height: 2; color: #606266; font-size: 13px; }
.guide-list code { background: #f0f2f5; border-radius: 4px; padding: 1px 5px; color: #8b5cf6; }
.guide-note { margin-top: 8px; font-size: 12px; color: #909399; background: #eef4ff; border-radius: 6px; padding: 8px 12px; }
</style>
