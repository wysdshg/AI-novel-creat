<template>
  <div>
    <el-card shadow="never" class="na-tip">
      <b>模块3 · 剧情商讨缓存（需求 6）</b>
      <span class="na-stub-tip"> 闲聊商讨仅缓存；生成指令汇总商讨记录+资料库+记忆+伏笔后生成。</span>
    </el-card>

    <el-row :gutter="16">
      <el-col :span="16">
        <el-card header="商讨会话" shadow="never" class="na-chat-card">
          <div class="na-chat">
            <p class="na-stub-tip">（商讨消息流占位，调用 discussionApi.list / append）</p>
          </div>
          <el-input v-model="input" placeholder="输入剧情讨论…" @keyup.enter="send">
            <template #append><el-button @click="send">发送</el-button></template>
          </el-input>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card header="缓存操作" shadow="never">
          <el-button @click="clear">清空临时缓存</el-button>
          <el-button type="primary" @click="archive">归档为章节备注</el-button>
          <p class="na-stub-tip na-mt">清空/归档调用 discussionApi.clear / archive</p>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { discussionApi } from '@/api/discussion'

const input = ref('')
const send = () => {
  // discussionApi.append(projectId, { role: 'user', content: input.value })
  console.log('[stub] send', input.value)
  input.value = ''
}
const clear = () => {
  // discussionApi.clear(projectId)
  console.log('[stub] clear')
}
const archive = () => {
  // discussionApi.archive(projectId, chapterId)
  console.log('[stub] archive')
}
</script>

<style scoped>
.na-tip { margin-bottom: 12px; }
.na-chat-card { height: 520px; }
.na-chat { flex: 1; overflow: auto; padding: 8px 0; }
.na-mt { margin-top: 12px; }
</style>
