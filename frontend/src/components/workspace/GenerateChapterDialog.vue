<template>
  <el-dialog
    :model-value="modelValue"
    title="生成章节"
    width="760px"
    top="5vh"
    :close-on-click-modal="!generating"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <div class="gcd-desc">
      按小说创作流程填写本章要素，作为结构化约束拼入 Prompt。仅「场景目标」必填，其余越具体 AI 越不易跑偏。
    </div>

    <template v-if="!generating && !result">
      <el-alert
        v-if="!effectiveArticleId"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        title="尚未选择所属篇"
        description="请先在左侧树中选择一篇或一章，再生成章节（章节必须归属于某一篇）。"
      />
      <el-form label-position="top" class="gcd-form">
        <el-form-item label="章节标题">
          <el-input v-model="title" placeholder="例如：第七章 · 宗门大比" />
        </el-form-item>
        <el-form-item label="章节序号">
          <el-input-number v-model="chapterNo" :min="1" />
          <span class="gcd-hint">在「某章对话」里打开＝生成/覆盖该章（沿用其章号，不新建）；在「篇/卷视图」打开＝接续本篇最大序号新建续章。</span>
        </el-form-item>

        <el-divider content-position="left">本章要素</el-divider>

        <ChapterElementsForm ref="formRef" />

        <el-form-item label="附加要求">
          <el-input
            v-model="extra"
            type="textarea"
            :rows="3"
            placeholder="温度 / 字数 / 特殊风格等补充说明（可选）"
            resize="none"
          />
        </el-form-item>
      </el-form>
    </template>

    <template v-else>
      <div class="gcd-status">
        <el-icon v-if="generating" class="is-loading"><Loading /></el-icon>
        <el-tag :type="generating ? 'warning' : stopped ? 'danger' : (result ? 'success' : 'info')">
          {{ generating ? '生成中…' : stopped ? '已停止' : (result ? `已生成（${wordCount} 字）` : '未开始') }}
        </el-tag>
        <el-tag v-if="stopReason" size="small" type="warning" effect="plain">{{ stopReason }}</el-tag>
        <el-tag v-if="ctx" size="small" type="info" effect="plain">
          上下文 {{ ctx.total_chars }} 字 · 占预算 {{ ctx.budget?.usage_pct ?? 0 }}%
        </el-tag>
        <el-tag v-if="thinkingActive" size="small" type="info" effect="plain">思考中…</el-tag>
        <el-tag v-if="ingestState" size="small" :type="ingestState.type" effect="plain">
          {{ ingestState.text }}
        </el-tag>
      </div>

      <!-- 这次 AI 到底读了什么：人设崩了能直接看出是没读到还是读了没听 -->
      <el-collapse v-if="ctx" class="gcd-ctx">
        <el-collapse-item name="ctx">
          <template #title>
            <span class="gcd-ctx-title">
              本次读取：{{ (ctx.budget?.kept || []).length }} 个上下文块
              <template v-if="(ctx.references || []).length">
                · {{ ctx.references.length }} 份参考资料
              </template>
              <template v-if="(ctx.skills?.active || []).length">
                · {{ ctx.skills.active.length }} 条 SKILL
              </template>
            </span>
          </template>
          <div class="gcd-ctx-body">
            <div class="gcd-ctx-row">
              <b>上下文块</b>
              <el-tag
                v-for="k in (ctx.budget?.kept || [])"
                :key="k.key"
                size="small"
                effect="plain"
              >{{ blockLabel(k.key) }} {{ k.chars }}字</el-tag>
            </div>
            <div v-if="(ctx.budget?.dropped || []).length" class="gcd-ctx-row">
              <b>因预算丢弃</b>
              <el-tag
                v-for="d in ctx.budget.dropped"
                :key="d.key"
                size="small"
                type="danger"
                effect="plain"
              >{{ blockLabel(d.key) }}</el-tag>
            </div>
            <div v-if="(ctx.references || []).length" class="gcd-ctx-row">
              <b>参考资料</b>
              <span class="gcd-ctx-text">
                {{ ctx.references.map((r) => r.filename).join('、') }}
              </span>
            </div>
            <div v-if="(ctx.skills?.active || []).length" class="gcd-ctx-row">
              <b>生效 SKILL</b>
              <el-tag
                v-for="s in ctx.skills.active"
                :key="s.name"
                size="small"
                type="success"
                effect="plain"
              >{{ s.name }}</el-tag>
            </div>
            <div v-if="(ctx.skills?.suppressed || []).length" class="gcd-ctx-row">
              <b>被同类挤掉</b>
              <el-tag
                v-for="s in ctx.skills.suppressed"
                :key="s.id || s.name"
                size="small"
                type="info"
                effect="plain"
              >{{ s.name }}（{{ s.reason }}）</el-tag>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>

      <!-- AI 味检测报告 -->
      <div v-if="scanReport" class="gcd-scan" :class="scanLevelClass">
        <div class="gcd-scan-head">
          <span class="gcd-scan-score">{{ scanReport.score }}</span>
          <span class="gcd-scan-grade">{{ scanReport.grade }}</span>
          <span class="gcd-scan-meta">
            {{ scanReport.issue_count }} 处可疑 · 每千字 {{ scanReport.per_thousand }} 处
          </span>
          <div class="gcd-spacer" />
          <el-button size="small" text @click="showIssues = !showIssues">
            {{ showIssues ? '收起' : '查看明细' }}
          </el-button>
        </div>
        <div v-if="showIssues" class="gcd-scan-list">
          <div v-for="(is, i) in (scanReport.issues || []).slice(0, 40)" :key="i" class="gcd-issue">
            <el-tag size="small" :type="sevType(is.severity)" effect="plain">
              {{ is.category || is.type }}
            </el-tag>
            <code class="gcd-issue-hit">{{ is.matched }}</code>
            <span class="gcd-issue-ctx">{{ is.context }}</span>
            <span v-if="is.advice" class="gcd-issue-fix">→ {{ is.advice }}</span>
          </div>
          <div v-if="(scanReport.issues || []).length > 40" class="gcd-issue-more">
            还有 {{ scanReport.issues.length - 40 }} 处未展示
          </div>
        </div>
      </div>

      <el-input
        :model-value="streamText"
        type="textarea"
        :rows="scanReport ? 12 : 18"
        readonly
        resize="none"
        class="gcd-result"
        placeholder="生成结果将在此实时显示"
      />
    </template>

    <template #footer>
      <template v-if="generating">
        <el-button type="danger" plain :loading="true">生成中…</el-button>
        <el-button type="danger" plain @click="onStop">停止生成</el-button>
      </template>
      <template v-else>
        <el-button @click="emit('update:modelValue', false)">
          {{ result || stopped ? '关闭' : '取消' }}
        </el-button>
        <el-button type="primary" :disabled="!effectiveArticleId" @click="onRegenerateClick">
          {{ result || stopped ? '重新生成' : '生成章节' }}
        </el-button>
        <el-button v-if="result || stopped || streamText" @click="copyResult">复制正文</el-button>
    <el-button
      v-if="result || stopped || streamText"
      type="success"
      plain
      :loading="savingRef"
      @click="onSaveAsReference"
    >存为小说参考文档</el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import ChapterElementsForm from './ChapterElementsForm.vue'
import { generateChapterStream } from '@/api/chapter'
import { referenceApi } from '@/api/reference'
import { useProjectStore } from '@/store/project'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  projectId: { type: String, default: '' },
  articleId: { type: String, default: '' },
  enableThinking: { type: Boolean, default: true },
})
const emit = defineEmits(['update:modelValue'])

const store = useProjectStore()

// 有效的篇上下文：优先来自父组件传入的 articleId，其次当前选中的篇/章。
// 为空时禁止生成（后端也会 400 兜底），避免产出「孤儿章」（不挂在任何篇下、侧栏不显示）。
const effectiveArticleId = computed(() => {
  if (props.articleId) return props.articleId
  if (store.currentArticle?.id) return store.currentArticle.id
  if (store.currentChapter?.article_id) return store.currentChapter.article_id
  return ''
})

const title = ref('')
const chapterNo = ref(1)
const extra = ref('')
const formRef = ref(null)
// 重新生成目标章节 ID：首次生成后由后端回传，之后「重新生成」复用它（覆盖同章，不新建）
const lastChapterId = ref('')

const generating = ref(false)
const streamText = ref('')
const result = ref(false)
const wordCount = ref(0)

// 思考模式状态：模型仍在思考模式下生成，但具体 reasoning 文本不再展示给用户
const thinkingActive = ref(false)
// 生成序号：新一轮生成开始后，旧流（残留事件/慢吞吞的 finally）不得覆盖本轮 UI 状态
const genSeq = ref(0)
// 手动停止：AbortController 中止 fetch 流；后端收到客户端断开后关闭 LLM 连接，立即停止计费
const stopController = ref(null)
const stopped = ref(false)      // 手动停止（保留已生成内容，但未落库）
const stopReason = ref('')      // 后端复读检测截断等提示
// 走向建议由后台摄取异步落库，关闭弹窗后轻量延时刷新把它显示出来（问题2 可见化）
const ingestRefreshTimers = []
const clearIngestTimers = () => {
  while (ingestRefreshTimers.length) clearTimeout(ingestRefreshTimers.pop())
}
// 问题8：本轮生成是否已在对话里回过「已完成章节生成」消息（复制/存参考文档触发，每轮最多一次）
const genDonePosted = ref(false)

// 生成过程中后端回传的三类元信息
const ctx = ref(null)             // context 事件：这次读了哪些资料
const scanReport = ref(null)      // validate 事件：AI 味检测报告
const ingestState = ref(null)     // ingest 事件：记忆抽取 / 走向推送结果
const showIssues = ref(false)

const BLOCK_LABELS = {
  task: '本章任务',
  discussion: '商讨记录',
  world: '世界观',
  characters: '角色卡',
  entities: '势力地点',
  foreshadows: '伏笔',
  stage_memory: '阶段脉络',
  recent_memory: '最近章回顾',
  prev_tail: '上一章结尾',
  references: '参考资料',
}
const blockLabel = (k) => BLOCK_LABELS[k] || k

// 本篇内下一个章节序号 = 该篇已有最大章号 + 1（而非小说全局递增）。
// 修复问题6：避免跨篇序号混乱、且每次生成都让全局计数 +1。
const nextChapterNo = computed(() => {
  const aid = effectiveArticleId.value
  if (!aid) return 1
  let max = 0
  for (const v of (store.structure.volumes || [])) {
    for (const a of (v.articles || [])) {
      if (a.id === aid) {
        for (const c of (a.chapters || [])) {
          if (typeof c.chapter_no === 'number' && c.chapter_no > max) max = c.chapter_no
        }
      }
    }
  }
  return max + 1
})

const scanLevelClass = computed(() => {
  const s = scanReport.value?.score ?? 100
  if (s >= 80) return 'is-good'
  if (s >= 55) return 'is-warn'
  return 'is-bad'
})
const sevType = (s) => (s >= 3 ? 'danger' : s === 2 ? 'warning' : 'info')

// 打开时：在「某章对话」里 → 默认序号用当前章的章号；在「篇/卷视图」→ 本篇最大序号 +1
chapterNo.value = store.currentChapter?.chapter_no ?? nextChapterNo.value

// 关键修复：每次弹窗被（重新）打开时，复位全部生成状态，
// 否则上一次的 result=true 会残留，导致再次打开仍停在「生成结束」页、没有生成按钮。
// 组件常驻挂载（仅 el-dialog 显隐），关闭后 ref 不会销毁，必须手动复位。
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      generating.value = false
      result.value = false
      streamText.value = ''
      wordCount.value = 0
      thinkingActive.value = false
      stopped.value = false
      stopReason.value = ''
      ctx.value = null
      scanReport.value = null
      ingestState.value = null
      showIssues.value = false
      // 问题8：在「某章对话」里打开 → 生成目标就是当前这一章（覆盖更新，不新建下一章）；
      // 在「篇/卷视图」（未选中章）打开 → 新建续章（接续本篇最大序号）。
      const targetChapterId = store.currentChapterId || ''
      const isSameTarget = targetChapterId && targetChapterId === lastChapterId.value
      // 只有打开目标变化（或首次打开）时才清空表单；同一章的「重新生成」保留上次填写内容
      if (!isSameTarget) {
        title.value = ''
        extra.value = ''
        formRef.value?.reset()
      }
      genDonePosted.value = false
      formRef.value?.clearErrors()
      lastChapterId.value = targetChapterId
      chapterNo.value = store.currentChapter?.chapter_no ?? nextChapterNo.value
    } else {
      // 弹窗关闭：生成/重新生成后，走向建议已落在「被生成的章」线程（后端 chapter.id 路由），
      // 且生成完成时已 store.selectChapter 切到该章；此处再刷新一次对话，确保卡片显示（问题2/3）。
      store.loadDiscussion().catch(() => {})
    }
  },
)

const onGenerate = async () => {
  const projectId = props.projectId || store.currentNovelId
  if (!projectId) return ElMessage.warning('请先选择一本小说')
  if (!effectiveArticleId.value) return ElMessage.warning('请先在左侧选择一篇或一章，再生成章节')

  formRef.value?.clearErrors()
  const valid = formRef.value?.validate?.()
  if (!valid) return ElMessage.warning('请填写必填项')

  // 本轮序号：后续回调里所有状态写入都要校验，防止旧流覆盖新生成
  const mySeq = ++genSeq.value
  const elements = formRef.value?.getElements?.() ?? []
  const filled = elements.filter((e) => e.value && e.value.trim())
  const hintParts = filled.map((e) => `${e.label}：${e.value}`)
  if (extra.value.trim()) hintParts.push(extra.value.trim())
  const prompt_hint = [title.value ? `标题：${title.value}` : '', ...hintParts].filter(Boolean).join('\n')

  generating.value = true
  streamText.value = ''
  thinkingActive.value = false
  stopped.value = false
  stopReason.value = ''
  result.value = false
  wordCount.value = 0
  ctx.value = null
  scanReport.value = null
  ingestState.value = null
  showIssues.value = false
  genDonePosted.value = false
  clearIngestTimers()

  // 当前所在对话线程（章优先，否则会话）：用于打包商讨（问题4）+ 走向建议归位（问题2/3）。
  // 即「在哪一格对话框点的生成，结果就回到哪一格」。
  const threadChapterId = store.currentChapterId || null
  const threadConversationId = store.currentChapterId ? null : (store.currentConversationId || null)

  const body = {
    chapter_no: chapterNo.value,
    prompt_hint,
    from_discussion: true,
    trigger_foreshadow_ids: [],
    word_range: { min: 3000, max: 5000 },
    // 温度 0.75：实测+搜索结论——低温(0.4)+无重复惩罚是长文复读主因；0.75 兼顾连贯与多样性。
    // 后端另有兜底（为空时也用 0.75）+ 重复惩罚参数 + 复读检测，三层防复读。
    temperature: 0.75,
    enable_thinking: props.enableThinking,
    article_id: effectiveArticleId.value || null,
    title: title.value || null,
    chapter_id: lastChapterId.value || null,   // 非空 = 覆盖该章（重新生成）；空 = 新建
    thread_chapter_id: threadChapterId,
    thread_conversation_id: threadConversationId,
  }

  // 手动停止句柄：点「停止生成」即 abort，后端断开 LLM 连接（停止计费）
  stopController.value = new AbortController()

  try {
    await generateChapterStream(
    projectId,
    body,
    (event, data) => {
      if (mySeq !== genSeq.value) return // 已开新一轮生成，忽略旧流事件
      if (event === 'thinking') {
        // 思考模式已开启，但 reasoning 文本不再展示给用户
        thinkingActive.value = true
      } else if (event === 'chunk') {
        streamText.value += data.text || ''
        thinkingActive.value = false
      } else if (event === 'context') {
        ctx.value = data
      } else if (event === 'validate') {
        scanReport.value = data && data.score !== undefined ? data : null
      } else if (event === 'stopped') {
        // 后端复读检测截断：正文已截断但仍会落库，提示原因
        stopReason.value = data?.reason === 'detected_repetition'
          ? '检测到重复循环，正文已截断'
          : (data?.reason || '生成被中断')
      } else if (event === 'ingest_start') {
        ingestState.value = data?.async
          ? { type: 'info', text: '记忆抽取后台进行中（不阻塞）' }
          : { type: 'warning', text: '正在抽取本章记忆…' }
      } else if (event === 'saved') {
        // 记录生成的章节 ID：后续「重新生成」将覆盖它，而不是新建一章（问题3）
        lastChapterId.value = data?.chapter_id || lastChapterId.value
      } else if (event === 'ingest') {
        if (data.error) {
          ingestState.value = { type: 'danger', text: '记忆抽取失败' }
        } else {
          const bits = []
          if (data.memory_id) bits.push('记忆已存')
          if (data.directions_pushed) bits.push(`${data.directions_pushed} 条走向已推送`)
          if ((data.new_entities || []).length) bits.push(`${data.new_entities.length} 个新实体待确认`)
          if (data.stage_compressed) bits.push('阶段摘要已压缩')
          ingestState.value = {
            type: data.fallback ? 'warning' : 'success',
            text: (data.fallback ? '兜底抽取：' : '') + (bits.join(' · ') || '已处理'),
          }
        }
      } else if (event === 'done') {
        wordCount.value = data.word_count || streamText.value.length
        lastChapterId.value = data?.chapter_id || lastChapterId.value
        result.value = true
        generating.value = false // done 即完成：摄取已在后台，无需等流关闭
      }
    }, { signal: stopController.value.signal, modelId: store.currentModelId })
    if (mySeq !== genSeq.value) return
    result.value = true
    // 4 级结构：生成后刷新侧栏树，让新章出现在对应篇下
    try {
      await store.loadStructure(projectId)
    } catch {
      /* 刷新失败不影响已生成结果 */
    }
    // 问题2 修复：生成完后把工作区切到「被生成的这一章」，走向建议卡片自然落在
    // 「该章的对话框」而不是小说级默认线程。结构已刷新，章必在树中。
    if (lastChapterId.value) {
      try {
        store.selectChapter(lastChapterId.value)
      } catch {
        /* 结构未就绪则跳过，卡片仍会落在正确章线程，用户手动点开即可见 */
      }
    }
    // 走向建议由后台摄取异步落库（云模型几秒、本地4b较慢），多轮轻量刷新把它显示出来。
    clearIngestTimers()
    for (const ms of [8000, 22000]) {
      ingestRefreshTimers.push(
        setTimeout(() => {
          if (mySeq === genSeq.value) store.loadDiscussion().catch(() => {})
        }, ms),
      )
    }
    ElMessage.success('章节生成完成')
  } catch (e) {
    if (mySeq !== genSeq.value) return
    if (e?.name === 'GenerationStopped') {
      // 用户手动停止：保留已生成内容，但不落库
      stopped.value = true
      ElMessage.info('已停止生成（保留已生成内容）')
      return
    }
    ElMessage.error('生成失败：' + (e?.message || e))
  } finally {
    if (mySeq === genSeq.value) {
      generating.value = false
      stopController.value = null
    }
  }
}

// 手动停止：abort 后 fetch 流抛出 GenerationStopped，上方 catch 处理 UI
const onStop = () => {
  stopController.value?.abort()
}

// 「重新生成」先返回表单页并保留填写内容，用户可修改后再点「生成章节」
const onRegenerateClick = () => {
  if (result.value || stopped.value) {
    result.value = false
    stopped.value = false
    streamText.value = ''
    wordCount.value = 0
    scanReport.value = null
    stopReason.value = ''
    return
  }
  onGenerate()
}

const copyResult = async () => {
  try {
    await navigator.clipboard.writeText(streamText.value)
    ElMessage.success('已复制正文')
    postGenDone('copy')
  } catch {
    ElMessage.warning('复制失败，请手动选择文本复制')
  }
}

// 问题8：在「点生成章节按钮」的那个对话下回一条「已完成章节生成」消息。
// 触发时机：本轮生成成功（result=true）后，用户点「复制正文」或「存为小说参考文档」；
// 每轮生成只回一次（genDonePosted 防重复）。appendPersistedMessage 按当前线程落库
// （章对话→章线程；篇视图新建章后已切到该章→该章线程），与走向建议落在同一处。
const postGenDone = async (action) => {
  if (!result.value || genDonePosted.value) return
  if (!store.currentNovelId || !lastChapterId.value) return
  genDonePosted.value = true
  const chTitle = title.value ? `《${title.value}》` : ''
  const actText = action === 'save' ? '，已存入小说参考文档' : action === 'copy' ? '，已复制正文' : ''
  const wc = wordCount.value || streamText.value.length || 0
  const content = `✅ 已完成第${chapterNo.value}章${chTitle}生成（${wc} 字）${actText}`
  // 本地先显示，再持久化到当前对话线程（与 /章节 等指令同一机制）
  store.discussionMessages.push({ role: 'ai', content })
  await store.appendPersistedMessage('ai', content, {
    type: 'chapter_done',
    chapter_id: lastChapterId.value,
    chapter_no: chapterNo.value,
  })
}

// 一键将生成正文存入「本小说级参考文档」（project_id 维度、article_id 为空、source=upload，
// 与全局参考资料池隔离）。后端 create_reference 自动生成 summary/tags，无需前端传。
const savingRef = ref(false)
const onSaveAsReference = async () => {
  const projectId = props.projectId || store.currentNovelId
  if (!projectId) return ElMessage.warning('请先选择一本小说')
  if (!streamText.value.trim()) return ElMessage.warning('暂无可保存的正文')
  // 文件名：优先用章标题，否则按章序号；去除文件系统非法字符
  const safe = (s) => (s || '').replace(/[\\/:*?"<>|\n\r\t]+/g, '').trim().slice(0, 60)
  const base = safe(title.value) || `第${chapterNo.value}章`
  const filename = `${base}_正文.txt`
  const contentText = streamText.value
  savingRef.value = true
  try {
    await referenceApi.upload(projectId, {
      filename,
      content_type: 'text/plain',
      size: new Blob([contentText]).size,
      content_text: contentText,
    })
    ElMessage.success(`已存入小说参考文档：${filename}`)
    postGenDone('save')
  } catch (e) {
    ElMessage.error('保存失败：' + (e?.response?.data?.message || e?.message || e))
  } finally {
    savingRef.value = false
  }
}
</script>

<style scoped>
.gcd-desc {
  font-size: 13px;
  color: #909399;
  margin-bottom: 12px;
}
.gcd-form { max-height: 62vh; overflow-y: auto; padding-right: 4px; }
.gcd-hint { font-size: 12px; color: #909399; margin-left: 10px; }
.gcd-status { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.gcd-result :deep(.el-textarea__inner) {
  font-size: 14px;
  line-height: 1.7;
  background: #fafafa;
}
.gcd-spacer { flex: 1; }

/* —— 上下文透明化面板 —— */
.gcd-ctx { margin-bottom: 10px; border-top: none; }
.gcd-ctx :deep(.el-collapse-item__header) { height: 34px; line-height: 34px; font-size: 12px; }
.gcd-ctx-title { color: #606266; font-size: 12px; }
.gcd-ctx-body { display: flex; flex-direction: column; gap: 8px; }
.gcd-ctx-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 12px;
}
.gcd-ctx-row b { color: #909399; font-weight: 500; min-width: 68px; }
.gcd-ctx-text { color: #606266; }


/* —— AI 味检测面板 —— */
.gcd-scan {
  border: 1px solid var(--el-border-color-light);
  border-left-width: 3px;
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 10px;
  background: #fafafa;
}
.gcd-scan.is-good { border-left-color: #67c23a; }
.gcd-scan.is-warn { border-left-color: #e6a23c; }
.gcd-scan.is-bad { border-left-color: #f56c6c; }
.gcd-scan-head { display: flex; align-items: center; gap: 10px; }
.gcd-scan-score { font-size: 20px; font-weight: 700; color: #303133; }
.gcd-scan-grade { font-size: 13px; font-weight: 600; color: #606266; }
.gcd-scan-meta { font-size: 12px; color: #909399; }
.gcd-scan-list {
  margin-top: 8px;
  max-height: 220px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.gcd-issue {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
  flex-wrap: wrap;
  padding-bottom: 5px;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.gcd-issue-hit {
  background: #fff0f0;
  color: #d94545;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: inherit;
}
.gcd-issue-ctx { color: #909399; flex: 1; min-width: 200px; }
.gcd-issue-fix { color: #67c23a; }
.gcd-issue-more { font-size: 12px; color: #909399; text-align: center; }
</style>
