<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { tiles, type Heatmap, type HeatStock, type HeatBoard, type Rect } from '@/api/heatmap'

const data = ref<Heatmap>(), error = ref(''), loading = ref(false), selected = ref(''), search = ref('')
const host = ref<HTMLElement>(), canvas = ref<HTMLCanvasElement>()
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
  ctx.scale(dpr, dpr); ctx.fillStyle = '#141a22'; ctx.fillRect(0, 0, width, height)
  hits = []; hover.value = undefined
  const boards = data.value?.boards.filter(b => !selected.value || b.code === selected.value) ?? []
  const query = search.value.trim().toLowerCase()
  for (const { item: board, box } of tiles(boards, { x: 0, y: 0, w: width, h: height })) {
    ctx.fillStyle = color(board.change); ctx.fillRect(box.x + 1, box.y + 1, box.w - 2, box.h - 2)
    ctx.save(); ctx.beginPath(); ctx.rect(box.x + 4, box.y, Math.max(0, box.w - 8), 24); ctx.clip()
    ctx.fillStyle = '#fff'; ctx.font = 'bold 13px sans-serif'; ctx.textAlign = 'left'
    ctx.fillText(`${board.name}  ${pct(board.change)}  涨${board.up} 跌${board.down}`, box.x + 6, box.y + 17); ctx.restore()
    for (const { item: stock, box: r } of tiles(board.children, { x: box.x + 2, y: box.y + 25, w: box.w - 4, h: box.h - 27 })) {
      const match = !query || stock.name.toLowerCase().includes(query) || stock.code.includes(query)
      ctx.globalAlpha = match ? 1 : .2
      ctx.fillStyle = color(stock.change); ctx.fillRect(r.x, r.y, Math.max(0, r.w - 1), Math.max(0, r.h - 1))
      if (r.w > 30 && r.h > 25) {
        const font = Math.max(10, Math.min(32, r.w / Math.max(stock.name.length, 4) * .83, r.h / 3.5))
        ctx.save(); ctx.beginPath(); ctx.rect(r.x + 2, r.y + 1, r.w - 4, r.h - 2); ctx.clip()
        ctx.fillStyle = '#fff'; ctx.font = `bold ${font}px sans-serif`; ctx.textAlign = 'center'
        ctx.fillText(stock.name, r.x + r.w / 2, r.y + r.h / 2 - 1)
        ctx.fillText(pct(stock.change), r.x + r.w / 2, r.y + r.h / 2 + font + 1)
        ctx.restore()
      }
      ctx.globalAlpha = 1
      hits.push({ stock, board, box: r })
    }
  }
}
function move(event: PointerEvent) {
  const rect = canvas.value!.getBoundingClientRect(), x = event.clientX - rect.left, y = event.clientY - rect.top
  const hit = hits.find(h => x >= h.box.x && x <= h.box.x + h.box.w && y >= h.box.y && y <= h.box.y + h.box.h)
  hover.value = hit ? { ...hit, x: Math.max(4, Math.min(x + 14, rect.width - 258)), y: Math.max(4, Math.min(y + 14, rect.height - 206)) } : undefined
}
watch([selected, search], draw)
onMounted(() => {
  observer = new ResizeObserver(draw); if (host.value) observer.observe(host.value)
  void refresh(); timer = setInterval(() => void refresh(), 60000)
})
onBeforeUnmount(() => { observer?.disconnect(); clearInterval(timer); controller?.abort() })
</script>

<template>
  <main class="heatmap-page">
    <div class="toolbar">
      <div><h1>大盘云图</h1><span>申万一级 · 收盘 {{ date || '—' }} · {{ data?.count ?? 0 }} 只股票</span></div>
      <div class="controls">
        <input v-model="search" aria-label="搜索股票" placeholder="搜索股票名称 / 代码" />
        <select v-model="selected" aria-label="选择行业"><option value="">全部行业</option><option v-for="b in data?.boards" :key="b.code" :value="b.code">{{ b.name }}</option></select>
        <button :disabled="loading" @click="refresh">{{ loading ? '更新中…' : '刷新' }}</button>
      </div>
    </div>
    <p class="legend">面积＝市值增减额绝对值 · <i class="red" />上涨 <i class="green" />下跌 <i class="gray" />平盘 · 颜色深浅表示涨跌幅，悬浮查看详情</p>
    <p v-if="error || data?.warning" class="notice" role="status">{{ error || data?.warning }}</p>
    <div ref="host" class="map">
      <canvas ref="canvas" aria-label="行业及成分股市值变化矩形树图，可通过行业筛选查看局部" @pointermove="move" @pointerleave="hover = undefined" @click="hover && (selected = hover.board.code)" />
      <div v-if="!data" class="empty" role="status">{{ loading ? '正在读取本地收盘行情…' : error || '暂无可用数据' }}</div>
      <div v-else-if="!hits.length" class="empty">暂无非零市值变化数据</div>
      <div v-if="hover" class="tooltip" :style="{ left: `${hover.x}px`, top: `${hover.y}px` }">
        <strong>{{ hover.stock.name }} <small>{{ hover.stock.code }}</small></strong>
        <div>{{ hover.board.name }} · {{ date }}</div>
        <div>收盘价 <b>{{ hover.stock.close.toFixed(2) }}</b></div>
        <div>涨跌幅 <b :style="{ color: hover.stock.change > 0 ? '#ff7b83' : '#4cdd92' }">{{ pct(hover.stock.change) }}</b></div>
        <div>总市值 <b>{{ money(hover.stock.totalMv) }}</b></div>
        <div>市值增减 <b>{{ hover.stock.deltaMv > 0 ? '+' : '' }}{{ money(hover.stock.deltaMv) }}</b></div>
        <small>点击放大行业，选择“全部行业”返回</small>
      </div>
    </div>
    <p class="footnote">对比前一交易日 {{ data?.previousDate }}；行业涨跌幅按成分股总市值净变化计算。{{ data?.missing ?? 0 }} 只缺少有效两日数据未计入，{{ data?.zero ?? 0 }} 只市值变化为零不占面积。重复归属优先划入成分股较少的行业，已去重 {{ data?.duplicates ?? 0 }} 项。盘中及当日校验完成前保留此前收盘数据。</p>
  </main>
</template>

<style scoped>
.heatmap-page{padding:14px 16px;color:var(--text);display:flex;flex-direction:column;gap:10px;min-height:calc(100vh - 80px)}
.toolbar,.controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.toolbar{justify-content:space-between}h1{font-size:20px;margin:0 0 4px}.toolbar span,.legend,.footnote{font-size:12px;color:var(--text-secondary)}
input,select,button{background:var(--bg-panel);color:var(--text);border:1px solid var(--border);border-radius:5px;padding:7px 10px}button{cursor:pointer}button:disabled{opacity:.5}.legend,.footnote{margin:0;line-height:1.8}.legend i{display:inline-block;width:10px;height:10px;margin:0 4px 0 10px}.red{background:#e54652}.green{background:#15b65e}.gray{background:#525a64}
.map{position:relative;width:100%;height:calc(100vh - 240px);min-height:450px;background:#141a22;border:1px solid var(--border);overflow:hidden}canvas{display:block;width:100%;height:100%;cursor:crosshair}.empty{position:absolute;inset:0;display:grid;place-items:center;color:#b9c3d0;pointer-events:none}.tooltip{position:absolute;width:240px;padding:12px;background:rgba(18,24,34,.96);color:#eff4fb;box-shadow:0 4px 20px #0008;border:1px solid #657086;border-radius:6px;pointer-events:none;font-size:12px;line-height:1.9}.tooltip strong{font-size:16px}.tooltip div{display:flex;justify-content:space-between}.tooltip small{color:#b3bdcd}.notice{padding:8px 12px;background:#bf8b2022;color:var(--text);font-size:13px;margin:0}@media(max-width:700px){.heatmap-page{padding:10px}.controls{gap:6px}.controls input{width:160px}.map{height:65vh}.toolbar span{font-size:11px}}
</style>
