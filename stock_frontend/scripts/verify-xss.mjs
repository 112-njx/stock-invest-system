/**
 * G30 安全回归测试：Markdown 渲染输出的 XSS 消毒验证。
 *
 * 做法：用 esbuild 打包真实的 src/utils/markdown.ts → 在 jsdom 下渲染 XSS payload
 * → 解析输出 DOM，断言不存在可执行元素/事件属性/javascript: 协议。
 *
 * 为什么用 DOM 解析而不是正则扫字符串：渲染器是 escape-first 的，
 * 转义后的 `&lt;script&gt;` 是惰性文本，正则会把无害文本误判为注入。
 *
 * 运行：npm run verify:xss
 */
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { rmSync } from 'node:fs'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const OUT = resolve(ROOT, 'node_modules/.cache/_markdown_bundle.mjs')

await build({
  entryPoints: [resolve(ROOT, 'src/utils/markdown.ts')],
  bundle: true,
  format: 'esm',
  outfile: OUT,
  platform: 'browser',
  logLevel: 'error',
})

// jsdom 提供 window/document 供 DOMPurify 使用
const dom = new JSDOM('<!DOCTYPE html><body></body>')
globalThis.window = dom.window
globalThis.document = dom.window.document
globalThis.Node = dom.window.Node
globalThis.HTMLElement = dom.window.HTMLElement
globalThis.HTMLBodyElement = dom.window.HTMLBodyElement

const { renderMarkdown } = await import(pathToFileURL(OUT).href)

/** XSS 攻击面样本：脚本/事件/协议/框架/表单/CSS 注入/编码绕过 */
const PAYLOADS = [
  '<script>alert(1)</script>',
  '<img src=x onerror=alert(1)>',
  '<img src=x onerror="alert(1)">',
  '<img src=x onerror=alert(1) src=y>',
  '[click](javascript:alert(1))',
  '[click](JaVaScRiPt:alert(1))',
  '[click](data:text/html,<script>alert(1)</script>)',
  '<iframe src="javascript:alert(1)"></iframe>',
  '<object data="data:text/html,<script>alert(1)</script>"></object>',
  '<embed src="data:text/html,<script>alert(1)</script>">',
  '<form action="//evil"><input name=x></form>',
  '<div style="background:url(javascript:alert(1))">x</div>',
  '<svg/onload=alert(1)>',
  '<svg><script>alert(1)</script></svg>',
  '<a href="javascript:alert(1)">x</a>',
  '<body onload=alert(1)>',
  '<math><mtext><script>alert(1)</script></mtext></math>',
  '**bold** <script>alert(1)</script> `code`',
  '<base href="//evil.com">',
  '<meta http-equiv="refresh" content="0;url=//evil">',
  '<textarea><script>alert(1)</script></textarea>',
  '<button onclick=alert(1)>x</button>',
]

const BAD_TAGS = new Set([
  'script', 'iframe', 'object', 'embed', 'form', 'input', 'textarea',
  'button', 'svg', 'math', 'base', 'meta', 'link', 'style',
])
const BAD_URI = /^\s*(javascript|data|vbscript):/i

/** 解析渲染结果 DOM，返回危险点列表（空数组=安全） */
function inspect(html) {
  const root = dom.window.document.createElement('div')
  root.innerHTML = html
  const problems = []
  root.querySelectorAll('*').forEach((el) => {
    const tag = el.tagName.toLowerCase()
    if (BAD_TAGS.has(tag)) problems.push(`<${tag}>`)
    for (const attr of el.attributes) {
      const n = attr.name.toLowerCase()
      if (n.startsWith('on')) problems.push(`${tag}[${n}]`)
      if (n === 'style') problems.push(`${tag}[style]`)
      if ((n === 'href' || n === 'src' || n === 'xlink:href') && BAD_URI.test(attr.value)) {
        problems.push(`${tag}[${n}=${attr.value.slice(0, 24)}]`)
      }
    }
  })
  return problems
}

let failed = 0
console.log('--- XSS payload 消毒检查（DOM 解析判定）---')
for (const p of PAYLOADS) {
  const problems = inspect(renderMarkdown(p))
  const ok = problems.length === 0
  if (!ok) failed++
  console.log(`${ok ? 'PASS' : 'FAIL'}  in=${JSON.stringify(p)}`)
  if (!ok) console.log(`      out=${renderMarkdown(p)}\n      problems=${problems.join(', ')}`)
}

console.log('\n--- 正常内容保留检查（消毒不得误伤）---')
const LEGIT = [
  ['**粗体**', /<strong>粗体<\/strong>/],
  ['`code`', /<code>code<\/code>/],
  ['# 标题', /<h1>标题<\/h1>/],
  ['- a\n- b', /<ul>[\s\S]*<li>a<\/li>[\s\S]*<li>b<\/li>[\s\S]*<\/ul>/],
  ['[链接](https://example.com)', /<a href="https:\/\/example\.com"[^>]*>链接<\/a>/],
  ['| a | b |\n| --- | --- |\n| 1 | 2 |', /<table>[\s\S]*<th>a<\/th>[\s\S]*<td>1<\/td>/],
]
for (const [src, re] of LEGIT) {
  const html = renderMarkdown(src)
  const ok = re.test(html)
  if (!ok) failed++
  console.log(`${ok ? 'PASS' : 'FAIL'}  in=${JSON.stringify(src)}  out=${html.replace(/\n/g, '')}`)
}

// 外链须保留 target="_blank" + rel=noopener（防 tabnabbing，且不改动原有 UX）
const linkHtml = renderMarkdown('[链接](https://example.com)')
const linkOk = /target="_blank"/.test(linkHtml) && /rel="noopener/.test(linkHtml)
if (!linkOk) failed++
console.log(`${linkOk ? 'PASS' : 'FAIL'}  外链保留 target=_blank + rel=noopener  out=${linkHtml}`)

rmSync(OUT, { force: true })
console.log(`\n结果：${failed === 0 ? '全部通过' : `${failed} 项失败`}`)
process.exit(failed === 0 ? 0 : 1)
