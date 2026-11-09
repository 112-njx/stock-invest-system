<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useThemeStore } from '@/stores/theme'
import { tiles, type Heatmap, type HeatStock, type HeatBoard, type Rect } from '@/api/heatmap'

const data = ref<Heatmap>(), error = ref(''), loading = ref(false), selected = ref('')
const theme = useThemeStore()
const hasTiles = ref(false)
const host = ref<HTMLElement>(), canvas = ref<HTMLCanvasElement>()
const picked = ref<{ stock: HeatStock; board: HeatBoard }>()
const hover = ref<{ stock: HeatStock; board: HeatBoard; x: number; y: number }>()
let hits: { stock: HeatStock; board: HeatBoard; box: Rect }[] = []
let observer: ResizeObserver | undefined, timer: ReturnType<typeof setInterval> | undefined
let controller: AbortController | undefined
const pct = (n: number) => `${n > 0 ? '+' : ''}${n.toFixed(2)}%`
const money = (n: number) => `${(n / 1e8).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 亿`
const date = computed(() => String(data.value?.date ?? '').replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3'))
const color = (n: number) => n === 0 ? '#525a64' : `hsl(${n > 0 ? 356 : 141} ${Math.min(85, 42 + Math.abs(n) * 7)}% ${Math.min(49, 28 + Math.abs(n) * 3)}%)`

async function refresh() {
  if (loading.value) return
  loading.value = true
  controller = new AbortController()
  const timeout = setTimeout(() => controller?.abort(), 45000)
  try {
    const response = await fetch('/api/v1/stockdb/heatmap', { signal: controller.signal })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new Error(body.detail || '云图数据读取失败')
    }
    data.value = await response.json()
    error.value = ''
    draw()
  } catch (e) { error.value = e instanceof Error ? e.message : '云图数据读取失败' }
  finally { clearTimeout(timeout); loading.value = false }
}
function draw() {
  const el = canvas.value, container = host.value
  if (!el || !container) return
  const width = container.clientWidth, height = container.clientHeight, dpr = window.devicePixelRatio || 1
  el.width = width * dpr; el.height = height * dpr
  const ctx = el.getContext('2d')
  if (!ctx) return
  ctx.scale(dpr, dpr); ctx.fillStyle = getComputedStyle(container).getPropertyValue('--bg-panel').trim(); ctx.fillRect(0, 0, width, height)
  hits = []; hover.value = undefined
  const boards = data.value?.boards.filter(b => !selected.value || b.code === selected.value) ?? []
  for (const { item: board, box } of tiles(boards, { x: 0, y: 0, w: width, h: height })) {
    ctx.fillStyle = color(board.change); ctx.fillRect(box.x + 1, box.y + 1, box.w - 2, box.h - 2)
    ctx.save(); ctx.beginPath(); ctx.rect(box.x + 4, box.y, Math.max(0, box.w - 8), 24); ctx.clip()
    ctx.fillStyle = '#fff'; ctx.font = 'bold 13px sans-serif'; ctx.textAlign = 'left'
    ctx.fillText(`${board.name}  ${pct(board.change)}  涨${board.up} 跌${board.down}`, box.x + 6, box.y + 17); ctx.restore()
    for (const { item: stock, box: r } of tiles(board.children, { x: box.x + 2, y: box.y + 25, w: box.w - 4, h: box.h - 27 })) {
      ctx.fillStyle = color(stock.change); ctx.fillRect(r.x, r.y, Math.max(0, r.w - 1), Math.max(0, r.h - 1))
      if (r.w > 30 && r.h > 25) {
        const font = Math.max(10, Math.min(32, r.w / Math.max(stock.name.length, 4) * .83, r.h / 3.5))
        ctx.save(); ctx.beginPath(); ctx.rect(r.x + 2, r.y + 1, r.w - 4, r.h - 2); ctx.clip()
        ctx.fillStyle = '#fff'; ctx.font = `bold ${font}px sans-serif`; ctx.textAlign = 'center'
        ctx.fillText(stock.name, r.x + r.w / 2, r.y + r.h / 2 - 1)
        ctx.fillText(pct(stock.change), r.x + r.w / 2, r.y + r.h / 2 + font + 1)
        ctx.restore()
      }
      hits.push({ stock, board, box: r })
    }
  }
  hasTiles.value = hits.length > 0
}
function hitAt(event: MouseEvent) {
  const rect = canvas.value!.getBoundingClientRect()
  const x = event.clientX - rect.left
  const y = event.clientY - rect.top
  const hit = hits.find(h => x >= h.box.x && x <= h.box.x + h.box.w && y >= h.box.y && y <= h.box.y + h.box.h)
  return { rect, x, y, hit }
}
function pick(event: MouseEvent) {
  const { hit } = hitAt(event)
  if (('pointerType' in event && event.pointerType !== 'mouse') || matchMedia('(pointer: coarse)').matches) {
    picked.value = hit
  } else if (hit) {
    selected.value = hit.board.code
  }
}
function move(event: PointerEvent) {
  if (event.pointerType !== 'mouse') return
  const { rect, x, y, hit } = hitAt(event)
  hover.value = hit ? { ...hit, x: Math.max(4, Math.min(x + 14, rect.width - 258)), y: Math.max(4, Math.min(y + 14, rect.height - 206)) } : undefined
}
function escapeIndustry(event: KeyboardEvent) {
  if (event.key === 'Escape') { selected.value = ''; hover.value = undefined; picked.value = undefined }
}
watch([selected, data], () => { picked.value = undefined })
watch([selected, () => theme.mode], draw, { flush: 'post' })
onMounted(() => {
  window.addEventListener('keydown', escapeIndustry)
  observer = new ResizeObserver(draw); if (host.value) observer.observe(host.value)
  void refresh(); timer = setInterval(() => void refresh(), 60000)
})
onBeforeUnmount(() => { window.removeEventListener('keydown', escapeIndustry); observer?.disconnect(); clearInterval(timer); controller?.abort() })
</script>

<template>
  <main class="heatmap-page">
    <div class="toolbar">
      <div class="heading"><h1>大盘云图</h1><div class="meta"><span>申万一级 · 收盘 {{ date || '—' }} · {{ data?.count ?? 0 }} 只股票</span><span class="legend">面积＝市值增减额绝对值 · <i class="red" />上涨 <i class="green" />下跌 <i class="gray" />平盘 · 颜色深浅表示涨跌幅，点按或悬浮查看详情</span></div></div>
      <div class="controls">
        <select v-model="selected" aria-label="选择行业"><option value="">全部行业</option><option v-for="b in data?.boards" :key="b.code" :value="b.code">{{ b.name }}</option></select>
        <button :disabled="loading" @click="refresh">{{ loading ? '更新中…' : '刷新' }}</button>
      </div>
    </div>
    <p v-if="error || data?.warning" class="notice" role="status">{{ error || data?.warning }}</p>
    <div ref="host" class="map">
      <canvas ref="canvas" aria-label="行业及成分股市值变化矩形树图，可通过行业筛选查看局部" @pointermove="move" @pointerleave="hover = undefined" @click="pick" />
      <div v-if="!data" class="empty" role="status">{{ loading ? '正在读取本地收盘行情…' : error || '暂无可用数据' }}</div>
      <div v-else-if="!hasTiles" class="empty">暂无非零市值变化数据</div>
      <div v-if="hover" class="tooltip" :style="{ left: `${hover.x}px`, top: `${hover.y}px` }">
        <strong>{{ hover.stock.name }} <small>{{ hover.stock.code }}</small></strong>
        <div>{{ hover.board.name }} · {{ date }}</div>
        <div>收盘价 <b>{{ hover.stock.close.toFixed(2) }}</b></div>
        <div>涨跌幅 <b :style="{ color: hover.stock.change > 0 ? '#ff7b83' : '#4cdd92' }">{{ pct(hover.stock.change) }}</b></div>
        <div>总市值 <b>{{ money(hover.stock.totalMv) }}</b></div>
        <div>市值增减 <b>{{ hover.stock.deltaMv > 0 ? '+' : '' }}{{ money(hover.stock.deltaMv) }}</b></div>
        <small>点击放大行业，按 Esc 返回全部行业</small>
      </div>
    </div>
    <section v-if="picked" class="tile-details" aria-label="云图股票详情">
      <header>
        <strong>{{ picked.stock.name }} · {{ picked.stock.code }}</strong>
        <button type="button" aria-label="关闭云图详情" @click="picked = undefined">关闭</button>
      </header>
      <p>{{ picked.board.name }} · {{ date }} · 收盘 {{ picked.stock.close.toFixed(2) }} · {{ pct(picked.stock.change) }}</p>
      <p>总市值 {{ money(picked.stock.totalMv) }} · 市值增减 {{ money(picked.stock.deltaMv) }}</p>
      <button v-if="selected !== picked.board.code" type="button" @click="selected = picked.board.code">放大该行业</button>
    </section>
  </main>
</template>

<style scoped>
.heatmap-page{padding:12px 16px 0;color:var(--text);display:flex;flex:1;min-height:0;flex-direction:column;gap:8px}
.toolbar,.controls{display:flex;align-items:center;gap:12px}.toolbar{justify-content:space-between;flex:none}.heading{min-width:0}h1{font-size:20px;margin:0 0 4px}.meta{display:flex;align-items:center;flex-wrap:wrap;gap:2px 14px;font-size:12px;color:var(--text-secondary);line-height:1.8}.controls{flex:none;align-self:flex-end}
select,button{background:var(--bg-panel);color:var(--text);border:1px solid var(--border);border-radius:5px;padding:7px 10px}button{cursor:pointer}button:disabled{opacity:.5}.legend i{display:inline-block;width:10px;height:10px;margin:0 4px 0 10px}.red{background:#e54652}.green{background:#15b65e}.gray{background:#525a64}
.map{position:relative;width:100%;flex:1;min-height:0;background:var(--bg-panel);border:1px solid var(--border);overflow:hidden}canvas{position:absolute;inset:0;display:block;width:100%;height:100%;cursor:crosshair}.empty{position:absolute;inset:0;display:grid;place-items:center;padding:20px;text-align:center;color:var(--text-secondary);background:var(--bg-panel);pointer-events:none}.tooltip{position:absolute;width:240px;padding:12px;background:var(--bg-panel);color:var(--text);box-shadow:0 4px 20px #0003;border:1px solid var(--border);border-radius:6px;pointer-events:none;font-size:12px;line-height:1.9}.tooltip strong{font-size:16px}.tooltip div{display:flex;justify-content:space-between}.tooltip small{color:var(--text-secondary)}.notice{padding:8px 12px;background:var(--bg-panel);border:1px solid var(--border);color:var(--text);font-size:13px;margin:0;flex:none}@media(max-width:700px){.heatmap-page{padding:8px 8px 0}.toolbar{align-items:flex-start;flex-wrap:wrap;gap:6px}.controls{margin-left:auto}.meta{font-size:11px}.legend{line-height:1.6}}
.tile-details { padding: 8px 12px; border: 1px solid var(--border); background: var(--bg-panel); }
.tile-details header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
@media (max-width: 767px), (max-width: 1023px) and (max-height: 500px) and (pointer: coarse) {
  .map { flex: none; height: var(--mobile-chart-height); }
  .controls { max-width: 100%; flex-wrap: wrap; }
  .controls select, .controls button, .tile-details button { min-height: var(--touch-target); }
}
</style>
