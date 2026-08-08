<template>
  <el-container class="na-layout">
    <!-- 左侧：小说 / 对话树 -->
    <el-aside width="248px" class="na-aside">
      <div class="na-logo">网页小说智能体</div>

      <div class="na-aside-actions">
        <el-button type="primary" class="na-new-novel" @click="onCreateNovel">
          <el-icon><Plus /></el-icon> 新建小说
        </el-button>
      </div>

      <div class="na-section-title">当前小说列表</div>
      <el-scrollbar class="na-tree-scroll">
        <el-tree
          class="na-tree"
          :data="novelTree"
          node-key="id"
          :props="{ label: 'label', children: 'children' }"
          :expand-on-click-node="false"
          default-expand-all
          highlight-current
          :current-node-key="store.currentNovelId"
          @node-click="onNodeClick"
        >
          <template #default="{ data }">
            <span class="na-tree-node" :class="`is-${data.type}`">
              <el-icon v-if="data.type === 'novel'"><Files /></el-icon>
              <el-icon v-else-if="data.type === 'dialogue'"><ChatDotRound /></el-icon>
              <el-icon v-else-if="data.action === 'config'"><MagicStick /></el-icon>
              <el-icon v-else><VideoPlay /></el-icon>
              <span class="na-tree-label">{{ data.label }}</span>
              <el-tag
                v-if="data.status"
                size="small"
                :type="data.statusType"
                effect="plain"
              >{{ data.status }}</el-tag>
              <el-button
                v-if="data.type === 'novel'"
                class="na-tree-del"
                size="small"
                text
                type="danger"
                title="删除小说"
                @click.stop="onDeleteNovel(data.id, data.label)"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </span>
          </template>
        </el-tree>
      </el-scrollbar>

      <div class="na-aside-footer">
        <router-link to="/workspace/model-config" class="na-model-link">
          <el-icon><Setting /></el-icon> 模型配置
        </router-link>
      </div>
    </el-aside>

    <!-- 右侧：顶部标签 + 内容 -->
    <el-container>
      <el-header class="na-header">
        <el-tabs :model-value="activeTab" class="na-tabs" @tab-change="onTabChange">
          <el-tab-pane
            v-for="t in tabs"
            :key="t.name"
            :name="t.name"
            :label="t.title"
          />
        </el-tabs>
      </el-header>

      <el-main class="na-main">
        <router-view />
      </el-main>
    </el-container>

    <!-- 生成章节弹窗：点击左侧「生成章节」节点时弹出 -->
    <GenerateChapterDialog v-model="generateVisible" />
    <!-- 新建小说弹窗 -->
    <CreateNovelDialog v-model="createVisible" />
  </el-container>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useProjectStore } from '@/store/project'
import GenerateChapterDialog from '@/components/workspace/GenerateChapterDialog.vue'
import CreateNovelDialog from '@/components/workspace/CreateNovelDialog.vue'

const route = useRoute()
const router = useRouter()
const store = useProjectStore()

// 「生成章节」弹窗显隐控制
const generateVisible = ref(false)
// 「新建小说」弹窗显隐控制
const createVisible = ref(false)

// 顶部标签由路由自动派生：所有 meta.tab=true 的子路由都会出现，
// 新增模块无需改动布局代码。
const tabs = computed(() =>
  router
    .getRoutes()
    .filter((r) => r.path.startsWith('/workspace/') && r.meta?.tab)
    .map((r) => ({ name: r.name, title: r.meta.title }))
)
const activeTab = computed(() => route.name)

const onTabChange = (name) => router.push({ name })

// 构建小说树：作品 → [配置对话, 生成章节, 对话A, 对话B, ...]
const novelTree = computed(() =>
  store.novels.map((n) => ({
    id: n.id,
    label: n.name,
    type: 'novel',
    children: [
      { id: `${n.id}:config`, label: '配置对话', type: 'action', action: 'config' },
      { id: `${n.id}:gen`, label: '生成章节', type: 'action', action: 'generate' },
      ...n.dialogues.map((d) => ({
        id: d.id,
        label: d.name,
        type: 'dialogue',
        status: d.status,
        statusType: d.statusType,
      })),
    ],
  }))
)

const onNodeClick = (data) => {
  if (data.type === 'novel') {
    // 点击小说节点即切换当前作品，让资料库/关系网等所有模块重新加载
    store.selectNovel(data.id)
  } else if (data.type === 'dialogue') {
    store.selectDialogue(data.id)
    router.push({ name: 'chat' })
  } else if (data.action === 'config') {
    // 「配置对话」节点：切到该小说并打开配置对话视图
    const novelId = String(data.id).split(':')[0]
    store.selectNovel(novelId)
    router.push({ name: 'config-chat' })
  } else if (data.action === 'generate') {
    generateVisible.value = true
  }
}

const onCreateNovel = () => { createVisible.value = true }

// 删除小说：二次确认后调 store.deleteNovel（后端级联清空该作品全部子表）
const onDeleteNovel = async (id, name) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除小说「${name}」吗？该作品下的角色、章节、伏笔等所有资料将一并删除，且不可恢复。`,
      '删除小说',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' }
    )
  } catch {
    return // 用户取消
  }
  try {
    await store.deleteNovel(id)
    ElMessage.success(`已删除小说「${name}」`)
  } catch (e) {
    ElMessage.error('删除失败：' + (e?.message || '未知错误'))
  }
}

// 应用启动后从后端拉取作品列表，使侧栏树、角色库等模块开箱可用
onMounted(() => {
  store.loadNovels().catch(() => ElMessage.warning('作品列表加载失败，请确认后端已启动'))
})
</script>

<style scoped>
.na-layout { height: 100vh; }
.na-aside {
  background: #1f2d3d;
  color: #fff;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.na-logo {
  height: 60px;
  line-height: 60px;
  text-align: center;
  font-weight: 600;
  font-size: 16px;
  color: #fff;
  border-bottom: 1px solid #2c3e50;
}
.na-aside-actions { padding: 12px; }
.na-new-novel { width: 100%; }
.na-section-title {
  padding: 8px 16px;
  font-size: 12px;
  color: #8a9bb0;
  letter-spacing: 1px;
}
.na-tree-scroll { flex: 1; }
.na-tree { background: transparent; }
.na-tree :deep(.el-tree-node__content) { background: transparent; color: #c0c4cc; height: 34px; }
.na-tree :deep(.el-tree-node__content:hover) { background: #2d3f53; }
.na-tree :deep(.el-tree-node.is-current > .el-tree-node__content) { background: #2f4b66; color: #fff; }
.na-tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
}
.na-tree-node.is-action .na-tree-label { color: #67c23a; }
.na-tree-label { flex: 1; overflow: hidden; text-overflow: ellipsis; }
.na-tree-del { margin-left: 2px; opacity: 0; transition: opacity .15s; color: #e06c75; }
.na-tree-node:hover .na-tree-del { opacity: 1; }
.na-aside-footer {
  border-top: 1px solid #2c3e50;
  padding: 12px 16px;
}
.na-model-link {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #c0c4cc;
  text-decoration: none;
}
.na-model-link:hover { color: #fff; }
.na-header {
  display: flex;
  align-items: center;
  background: #fff;
  border-bottom: 1px solid var(--el-border-color-light);
  padding: 0 16px;
}
.na-tabs { width: 100%; }
.na-tabs :deep(.el-tabs__header) { margin: 0; }
.na-main { padding: 16px; background: #f5f7fa; }
</style>
