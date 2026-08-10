// 解析用户输入中的显式 /指令，用于「配置对话」视图的确定性路由。
//
// 支持的指令：
//   /角色 <文本>        新增角色（文本交给 config 接口的自然语言抽取）
//   /地点 <文本>        新增地点
//   /势力 <文本>        新增势力
//   /设定 <文本>        整段自然语言，抽取角色+势力+地点+关系
//   /章节 <第X章> <要点> 生成章节正文
//
// 规则：
//   - 指令以 /指令 开头，到行尾或下一个 /指令 结束（无需结束符）。
//   - 同一条消息含多个指令时，按固定顺序执行：角色 → 地点 → 势力 → 设定 → 章节。
//   - 章节永远最后（它要引用前面已建的角色/地点/势力）。
//   - 不属于任何指令的自由文本，作为「设定」类自然语言一并发送（与无指令时的原行为一致）。

const ORDER = { 角色: 0, 地点: 1, 势力: 2, 设定: 3, 自由: 4, 章节: 99 }

// 匹配 /角色|地点|势力|设定|章节 + 其后内容（惰性，直到下一个指令或结尾）
const CMD_RE = /\/(角色|地点|势力|设定|章节)\s*([\s\S]*?)(?=\s*\/(?:角色|地点|势力|设定|章节)|$)/g

export function parseSlashCommands(raw) {
  const text = (raw || '').trim()
  if (!text) return []
  // 自然语言「添加/新增/新建/创建 + 实体类型」归一为 /指令，
  // 避免走「剧情商讨流」（那套带「给 2~3 个方向」指令，会让 AI 额外脑补一堆角色/势力）。
  // 只处理 角色/地点/势力 三类实体；章节/设定保持斜杠显式指令，避免误触。
  let normalized = text.replace(
    /(?:添加|新增|新建|创建)(?:了|个)?\s*(角色|地点|势力)/g,
    (_, t) => `/${t}`
  )
  const actions = []
  let lastIndex = 0
  let m
  CMD_RE.lastIndex = 0
  while ((m = CMD_RE.exec(normalized)) !== null) {
    const type = m[1]
    const content = (m[2] || '').trim().replace(/[，,、；;]$/g, '')
    // 当前指令之前的片段作为自由文本
    const before = normalized.slice(lastIndex, m.index).trim()
    if (before) actions.push({ kind: 'config', sub: '自由', text: before, order: ORDER['自由'] })
    lastIndex = CMD_RE.lastIndex
    if (type === '章节') {
      actions.push(makeChapter(content))
    } else if (content) {
      // 为单一实体指令补前缀，帮助后端模型从极简输入中正确抽取
      const prompt = type === '自由' || type === '设定' ? content : `新增${type === '设定' ? '设定/关系' : type}：${content}`
      actions.push({ kind: 'config', sub: type, text: content, prompt, order: ORDER[type] })
    }
  }
  // 结尾剩余自由文本
  const tail = normalized.slice(lastIndex).trim().replace(/^[，,、；;]+|[，,、；;]+$/g, '')
  if (tail) actions.push({ kind: 'config', sub: '自由', text: tail, order: ORDER['自由'] })

  actions.sort((a, b) => a.order - b.order)
  return actions
}

function makeChapter(content) {
  const numMatch = content.match(/第\s*(\d+)\s*章/) || content.match(/(\d+)/)
  const chapterNo = numMatch ? parseInt(numMatch[1], 10) : null
  // 去掉章节号标记，剩余作为生成要点
  let hint = content
  if (numMatch) {
    hint = content.replace(/第\s*\d+\s*章/, '').replace(/^\s*\d+\s*/, '').trim()
  }
  return { kind: 'chapter', chapterNo, hint, order: ORDER['章节'] }
}
