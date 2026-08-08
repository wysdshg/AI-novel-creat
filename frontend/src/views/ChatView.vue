<template>
  <el-container class="cv" direction="vertical">
    <!-- 工具条 -->
    <div class="cv-toolbar">
      <span class="cv-title">
        当前对话：{{ store.currentDialogue?.name || '未选择' }}
      </span>
      <el-switch
        v-model="plotLock"
        active-text="剧情锁"
        inactive-text="可生成"
        inline-prompt
      />
      <el-button size="small" @click="elementsVisible = !elementsVisible">
        本章要素 {{ elementsVisible ? '隐藏' : '显示' }}
      </el-button>
    </div>

    <!-- 主体：聊天 + 右侧本章要素 -->
    <el-container class="cv-body">
      <el-main class="cv-chat">
        <ChatPanel :messages="messages" />
      </el-main>
      <el-aside v-if="elementsVisible" width="340px" class="cv-elements">
        <ChapterElementsPanel />
      </el-aside>
    </el-container>

    <!-- 底部输入 -->
    <el-footer class="cv-input" height="auto">
      <ChatInput />
    </el-footer>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useProjectStore } from '@/store/project'
import ChatPanel from '@/components/workspace/ChatPanel.vue'
import ChapterElementsPanel from '@/components/workspace/ChapterElementsPanel.vue'
import ChatInput from '@/components/workspace/ChatInput.vue'

const store = useProjectStore()
const plotLock = ref(false)
const elementsVisible = ref(true)

onMounted(async () => {
  await store.loadNovels()
  store.loadModels()
  store.loadDiscussion()
})

// 对话消息来自 store（与 ChatInput 共享），发送后实时流式追加 AI 回复
const messages = computed(() => store.discussionMessages)
</script>

<style scoped>
.cv { height: 100%; }
.cv-toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 4px 12px;
}
.cv-title { font-weight: 600; }
.cv-body { flex: 1; overflow: hidden; }
.cv-chat { padding: 0 12px 0 0; overflow: hidden; }
.cv-elements { padding: 0; }
.cv-input { padding: 0; background: transparent; }
</style>
