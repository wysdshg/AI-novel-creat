// 解析全局参考资料中「人设模板」类 Markdown 文档，提取结构化模板列表。
//
// 约定格式（用户承诺保持统一）：
//   ## 1. 模板名称
//   - 字段名：字段值
//   - 字段名：字段值
//
// 兼容：H2/H3 标题作为模板起始；以「数字.」开头的纯文本行也视为模板标题；
// 其余以「-」或「*」开头的「键：值」行作为该模板的字段。

/**
 * 从人设模板 Markdown 文本解析出模板数组。
 * @param {string} text 参考文档正文
 * @returns {Array<{title:string, fields:Record<string,string>}>}
 */
export function parseCharacterTemplates(text) {
  if (!text || !text.trim()) return []
  const lines = text.split(/\r?\n/)
  const templates = []
  let cur = null

  const pushCur = () => {
    if (cur) templates.push(cur)
  }

  for (const raw of lines) {
    const line = raw.trim()
    if (!line) continue

    // 标题行：## 1. 落榜中年书生  /  ### 2. 世家纨绔公子
    const h = line.match(/^#{2,3}\s+(.+)$/)
    if (h) {
      pushCur()
      // 去掉标题开头可能的编号前缀（"1. " / "12、"），让下拉显示更干净
      const title = h[1].trim().replace(/^\d+[\.、)]\s*/, '')
      cur = { title, fields: {} }
      continue
    }

    // 编号标题行（无 ##，但形如「1. 模板名」且不含冒号）
    const num = line.match(/^\d+[\.、)]\s*(.+)$/)
    if (num && !line.includes('：') && !line.includes(':')) {
      pushCur()
      cur = { title: num[1].trim(), fields: {} }
      continue
    }

    // 字段行：- 性格：沉稳执拗  /  * 能力：八股功底扎实
    const item = line.match(/^[-*]\s*([^：:]+?)\s*[：:]\s*(.+)$/)
    if (item && cur) {
      const key = item[1].trim()
      const val = item[2].trim()
      if (key) cur.fields[key] = val
    }
  }
  pushCur()
  return templates
}

/**
 * 从「年龄段」文本取中间年龄。
 *   "中年 35~45"        → 40
 *   "青年~中年 25~50"   → 37
 *   "老年 55~70"        → 62
 *   "少年 12~18"        → 15
 * 仅有一个数字时直接返回该数字；无数字返回 null。
 * @param {string} ageText
 * @returns {number|null}
 */
export function parseAgeMid(ageText) {
  if (!ageText) return null
  const nums = (ageText.match(/\d+/g) || []).map(Number)
  if (!nums.length) return null
  if (nums.length === 1) return nums[0]
  return Math.round((nums[0] + nums[nums.length - 1]) / 2)
}
