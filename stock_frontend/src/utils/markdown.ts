/**
 * 极简 Markdown 渲染器（AI 输出流式渲染用）：
 * - 仅支持安全子集：标题/粗体/斜体/行内代码/代码块/无序有序列表/简单表格/链接/段落
 * - 先 HTML 转义再解析，白名单标签输出，无 XSS 注入面（不引入 marked+DOMPurify 依赖）
 * - 输出直接用于 v-html，配合样式文件中的 .markdown-body 命名空间
 *
 * 占位符：行内代码 / 代码块（在转义后替换，避免内嵌语法被二次解析）。
 */

const INLINE_PH = '\u0000'
const BLOCK_PH = '\u0001'

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** 行内语法：行内代码（占位保护）→ 粗体 → 斜体 → 链接 */
function inline(s: string): string {
  const codes: string[] = []
  let t = s.replace(/`([^`]+)`/g, (_m, c: string) => {
    codes.push(c)
    return `${INLINE_PH}${codes.length - 1}${INLINE_PH}`
  })
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  t = t.replace(/(^|[^*])\*([^*\s][^*]*?)\*(?!\*)/g, '$1<em>$2</em>')
  t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
  const re = new RegExp(`${INLINE_PH}(\\d+)${INLINE_PH}`, 'g')
  return t.replace(re, (_m, i: string) => `<code>${codes[+i]}</code>`)
}

/** 简单表格：行以 | 开头，第二行为分隔行（可选） */
function renderTable(rows: string[]): string {
  const cells = rows.map((r) => r.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map((c) => c.trim()))
  let body = cells
  const header = cells[0]
  if (body.length > 1 && body[1].every((c) => /^:?-{2,}:?$/.test(c))) {
    body = body.slice(2)
  } else {
    body = body.slice(1)
  }
  let html = '<table><thead><tr>'
  for (const c of header) html += `<th>${inline(c)}</th>`
  html += '</tr></thead><tbody>'
  for (const row of body) {
    html += '<tr>'
    for (let i = 0; i < header.length; i++) html += `<td>${inline(row[i] ?? '')}</td>`
    html += '</tr>'
  }
  return html + '</tbody></table>'
}

export function renderMarkdown(text: string): string {
  if (!text) return ''
  let src = escapeHtml(text)

  // 代码块保护（先于行级处理）
  const blocks: string[] = []
  src = src.replace(/```[^\n]*\n([\s\S]*?)```/g, (_m, code: string) => {
    blocks.push(code.replace(/\n$/, ''))
    return `${BLOCK_PH}${blocks.length - 1}${BLOCK_PH}`
  })

  const lines = src.split('\n')
  const out: string[] = []
  let listTag: 'ul' | 'ol' | null = null
  const closeList = () => {
    if (listTag) {
      out.push(`</${listTag}>`)
      listTag = null
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (!line.trim()) {
      closeList()
      continue
    }
    // 代码块占位
    const blkRe = new RegExp(`^${BLOCK_PH}(\\d+)${BLOCK_PH}$`)
    const blk = line.match(blkRe)
    if (blk) {
      closeList()
      out.push(`<pre><code>${blocks[+blk[1]]}</code></pre>`)
      continue
    }
    // 标题
    const h = line.match(/^(#{1,6})\s+(.*)$/)
    if (h) {
      closeList()
      out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`)
      continue
    }
    // 无序列表
    const ul = line.match(/^\s*[-*]\s+(.*)$/)
    if (ul) {
      if (listTag !== 'ul') {
        closeList()
        out.push('<ul>')
        listTag = 'ul'
      }
      out.push(`<li>${inline(ul[1])}</li>`)
      continue
    }
    // 有序列表
    const ol = line.match(/^\s*\d+\.\s+(.*)$/)
    if (ol) {
      if (listTag !== 'ol') {
        closeList()
        out.push('<ol>')
        listTag = 'ol'
      }
      out.push(`<li>${inline(ol[1])}</li>`)
      continue
    }
    // 表格（连续 | 开头行）
    if (line.trim().startsWith('|')) {
      const rows = [line.trim()]
      while (i + 1 < lines.length && lines[i + 1].trim().startsWith('|')) {
        rows.push(lines[++i].trim())
      }
      closeList()
      out.push(renderTable(rows))
      continue
    }
    // 普通段落
    closeList()
    out.push(`<p>${inline(line)}</p>`)
  }
  closeList()
  return out.join('\n')
}
