<template>
  <el-form :model="form" label-width="80px" class="cf">
    <!-- 人设模板（数据来自全局参考资料中文件名含「人设」的文档） -->
    <el-form-item label="人设模板">
      <div class="cf-tpl">
        <el-select
          v-model="tplFileId"
          placeholder="选择模板文件（可选）"
          :loading="tplLoading"
          style="width:100%"
          @change="onTplFileChange"
        >
          <el-option label="不使用模板" value="" />
          <el-option v-for="f in tplFiles" :key="f.id" :label="f.filename" :value="f.id" />
        </el-select>
        <el-select
          v-model="tplName"
          placeholder="选择具体人设"
          clearable
          filterable
          :disabled="!tplFileId || !tplList.length"
          style="width:100%; margin-top:8px"
          @change="onTplChange"
        >
          <el-option v-for="t in tplList" :key="t.title" :label="t.title" :value="t.title" />
        </el-select>
        <p v-if="tplError" class="cf-tpl-error">{{ tplError }}</p>
        <p v-else-if="tplFileId && tplList.length && !tplName" class="cf-tpl-tip">
          选择后将自动填充到下方空字段（不会覆盖已填写内容）
        </p>
      </div>
    </el-form-item>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-form-item label="姓名" required>
          <div class="cf-name-row">
            <el-input v-model="form.name" placeholder="角色姓名" />
            <el-button
              class="cf-rand-btn"
              :icon="Refresh"
              circle
              size="small"
              title="随机生成名字"
              @click="randomName"
            />
          </div>
        </el-form-item>
      </el-col>
      <el-col :span="12">
        <el-form-item label="地位">
          <el-select v-model="form.role_type" placeholder="选择地位" clearable style="width:100%">
            <el-option label="主角" value="主角" />
            <el-option label="配角" value="配角" />
            <el-option label="反派" value="反派" />
          </el-select>
        </el-form-item>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-form-item label="年龄">
          <el-input-number v-model="form.age" :min="0" :max="999" controls-position="right" style="width:100%" />
        </el-form-item>
      </el-col>
      <el-col :span="12">
        <el-form-item label="性别">
          <el-select v-model="form.gender" placeholder="选择性别" clearable style="width:100%">
            <el-option label="男" value="男" />
            <el-option label="女" value="女" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-form-item label="当前等级">
          <el-input v-model="form.current_level" placeholder="如：筑基初期 / Lv.12" />
        </el-form-item>
      </el-col>
    </el-row>

    <el-form-item label="性格">
      <el-input v-model="form.personality" type="textarea" :rows="2" resize="none" placeholder="性格特征…" />
    </el-form-item>

    <el-form-item label="背景">
      <el-input v-model="form.background" type="textarea" :rows="3" resize="none" placeholder="身世背景…" />
    </el-form-item>

    <el-form-item label="天赋">
      <el-input v-model="form.talent" type="textarea" :rows="2" resize="none" placeholder="天赋/资质…" />
    </el-form-item>

    <el-form-item label="技能">
      <el-select
        v-model="form.skills"
        multiple
        filterable
        allow-create
        default-first-option
        placeholder="输入技能后回车添加，可多个"
        style="width:100%"
      >
        <el-option v-for="s in form.skills" :key="s" :label="s" :value="s" />
      </el-select>
    </el-form-item>

    <el-form-item label="关系网">
      <el-select
        v-model="form.relationship_network"
        multiple
        filterable
        allow-create
        default-first-option
        placeholder="如：与苏晚·恋人（已反目），回车添加多条"
        style="width:100%"
      >
        <el-option v-for="r in form.relationship_network" :key="r" :label="r" :value="r" />
      </el-select>
    </el-form-item>

    <el-form-item label="简介">
      <el-input v-model="form.brief" type="textarea" :rows="3" resize="none" placeholder="一句话简介…" />
    </el-form-item>
  </el-form>
</template>

<script setup>
import { defineModel, ref, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { parseCharacterTemplates, parseAgeMid } from '@/utils/templateParser'

// 表单对象由父组件通过 v-model 传入，直接双向绑定
const form = defineModel({ type: Object, required: true })

// ============ 人设模板（来自全局参考资料「人设」类文档）============
const tplFiles = ref([])        // 候选模板文件列表（全局参考文档中文件名含「人设」）
const tplFileId = ref('')       // 选中的文件 id（''= 不使用模板）
const tplList = ref([])         // 该文件解析出的模板数组
const tplName = ref('')         // 选中的具体模板名
const tplLoading = ref(false)
const tplError = ref('')        // 参考文献无效的提示（不阻塞其它字段）

async function _fetchGlobalDocs() {
  const res = await fetch('/api/v1/references/global')
  if (!res.ok) throw new Error('HTTP ' + res.status)
  const json = await res.json()
  const arr = json?.data || json
  return Array.isArray(arr) ? arr : []
}

async function loadTplFiles() {
  try {
    const docs = await _fetchGlobalDocs()
    // 文件名含「人设」的全局参考文档视为角色模板文件
    tplFiles.value = docs.filter((d) => (d.filename || '').includes('人设'))
  } catch {
    tplFiles.value = []
  }
}

async function onTplFileChange(fileId) {
  tplName.value = ''
  tplList.value = []
  tplError.value = ''
  if (!fileId) return
  tplLoading.value = true
  try {
    const res = await fetch(`/api/v1/references/global/${fileId}`)
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const json = await res.json()
    const doc = json?.data || json
    const text = doc?.content_text
    if (!text || !text.trim()) {
      tplError.value = '该模板文件内容为空，无法解析'
      return
    }
    const list = parseCharacterTemplates(text)
    if (!list.length) {
      tplError.value = '该文件未解析出人设模板，请检查格式（需 ## 标题 + - 字段：值）'
      return
    }
    tplList.value = list
  } catch (e) {
    tplError.value = '模板文件读取失败：' + (e?.message || '未知错误')
  } finally {
    tplLoading.value = false
  }
}

function onTplChange(name) {
  if (!name) return
  const tpl = tplList.value.find((t) => t.title === name)
  if (tpl) applyTemplate(tpl)
}

// 把模板字段回填到表单「空字段」（不覆盖已有内容）
function applyTemplate(tpl) {
  const f = form.value
  const fields = tpl.fields || {}
  const age = parseAgeMid(fields['年龄段'])
  if (age != null && (f.age == null || f.age === '')) f.age = age
  if (fields['性格'] && !f.personality) f.personality = fields['性格']
  if (fields['经历'] && !f.background) f.background = fields['经历']
  if (fields['能力'] && !f.talent) f.talent = fields['能力']
  const briefParts = []
  if (fields['社会地位']) briefParts.push('【社会地位】' + fields['社会地位'])
  if (fields['其他补充']) briefParts.push(fields['其他补充'])
  if (briefParts.length && !f.brief) f.brief = briefParts.join('\n')
}

onMounted(loadTplFiles)

// —— 随机取名：从全局参考文档「取名素材」中随机拼名 ——
const _nameCache = ref(null) // { surnames: string[], maleNames: string[], femaleNames: string[] }

/** 从文本中提取名字：截掉「分类：」前缀，按空白分割，只留 1~3 字中文词 */
function _extractNames(text) {
  if (!text) return []
  return text
    .split(/\n/)
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('#')) // 去掉 markdown 标题行
    .map((l) => {
      // 去掉「双字名 | 玄幻/仙侠男主：」这类分类前缀，保留冒号后的名字
      const idx = l.indexOf('：')
      return idx >= 0 ? l.slice(idx + 1) : l
    })
    .join(' ')
    .split(/\s+/)
    .filter((w) => /^[\u4e00-\u9fa5]{1,3}$/.test(w)) // 仅 1~3 字纯中文
}

async function _ensureCache() {
  if (_nameCache.value) return _nameCache.value
  try {
    // 用原生 fetch 绕过 http 拦截器（避免 500 时弹 ElMessage.error）
    const [surnamesRes, maleRes, femaleRes] = await Promise.all([
      fetch('/api/v1/references/global/9f01a7f33b3f46479d7a77c0a4d1fb9e'),   // 取名素材·常见姓氏120
      fetch('/api/v1/references/global/483f3933d90748e9bcc53dc7e8978c3c'),   // 取名素材·男性小说名500
      fetch('/api/v1/references/global/d0fbcf87542d4881a18ea50aaf362ace'),   // 取名素材·女性小说名300
    ])
    const [surnamesData, maleData, femaleData] = await Promise.all([
      surnamesRes.json(), maleRes.json(), femaleRes.json(),
    ])
    // http 信封 {code:0, data: {...}}，取 data 字段
    const s = surnamesData.data || surnamesData
    const m = maleData.data || maleData
    const f = femaleData.data || femaleData
    _nameCache.value = {
      surnames: _extractNames(s.content_text),
      maleNames: _extractNames(m.content_text),
      femaleNames: _extractNames(f.content_text),
    }
  } catch {
    // 参考文档不可用时给个基础 fallback（静默，不弹错误）
    _nameCache.value = {
      surnames: ['林','顾','沈','苏','叶','陆','萧','秦','楚','白','谢','江','傅','裴','温','墨','厉','薄','姜','贺'],
      maleNames: ['辰','渊','麟','霄','珩','瑾','曜','煜','轩','泽','睿','皓','铭','翊','尘','锋','玄','昊'],
      femaleNames: ['瑶','汐','萱','芷','茉','恬','舒','妍','嫣','凝','沁','琳','菲','岚','苓','婉','娴','柔'],
    }
  }
  return _nameCache.value
}

async function randomName() {
  const cache = await _ensureCache()
  const surname = cache.surnames[Math.floor(Math.random() * cache.surnames.length)] || ''
  const isFemale = form.value.gender === '女'
  const pool = isFemale ? cache.femaleNames : cache.maleNames
  const given = pool[Math.floor(Math.random() * pool.length)] || ''
  form.value.name = `${surname}${given}`
}
</script>

<style scoped>
.cf { padding: 4px 8px 0; }
.cf-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cf-name-row .el-input { flex: 1; }
.cf-rand-btn { flex-shrink: 0; }
.cf-tpl { width: 100%; }
.cf-tpl-error { color: #f56c6c; font-size: 12px; margin: 6px 0 0; line-height: 1.4; }
.cf-tpl-tip { color: #909399; font-size: 12px; margin: 6px 0 0; line-height: 1.4; }
</style>
