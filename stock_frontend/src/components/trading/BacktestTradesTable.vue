<script setup lang="ts">
/**
 * G32（P1-11）· 回测交易明细表。
 *
 * 列：时间 / 方向 / 价格 / 数量 / 费用 / 累计持仓 / 已实现盈亏 / 触发原因。
 * 数值全部来自后端（G20 口径）：
 * - 已实现盈亏 = 后端 trades[].realized_pnl（复用 metrics._pair_trades 净盈亏，与胜率同口径）
 * - 累计持仓 = 逐笔 shares 的运行和（纯流水记账，非指标计算）
 *
 * 复用于：全景 K 线 D 区策略指标面板、AI 页 N 区策略详情。
 */
import { computed, ref } from 'vue'
import type { BacktestTrade } from '@/api/ai'

const props = withDefaults(
  defineProps<{
    trades: BacktestTrade[]
    /** 表格最大高度（超出滚动） */
    maxHeight?: string
  }>(),
  { maxHeight: '180px' }
)

/** 是否展示累计持仓列（小面板可关掉省横向空间） */
const showPos = ref(true)

const REASON_LABEL: Record<BacktestTrade['reason'], string> = {
  signal: '信号',
  stop_loss: '止损',
  take_profit: '止盈',
}

/** 逐笔累计持仓（买+卖-） */
const rows = computed(() => {
  let pos = 0
  return props.trades.map((t) => {
    pos += t.side === 'buy' ? t.shares : -t.shares
    return { ...t, cumPos: pos }
  })
})

function fmtTime(ts: string): string {
  const d = new Date(/(Z|[+-]\d{2}:?\d{2})$/.test(ts) ? ts : `${ts}Z`)
  if (Number.isNaN(d.getTime())) return ts
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function fmtMoney(v?: number | null): string {
  return v == null ? '--' : v.toFixed(2)
}
</script>

<template>
  <div class="tt">
    <div class="tt__head">
      <span class="tt__title">交易明细</span>
      <span class="tt__count">{{ trades.length }} 笔</span>
      <button class="tt__toggle" @click="showPos = !showPos">
        {{ showPos ? '隐藏持仓列' : '显示持仓列' }}
      </button>
    </div>

    <div v-if="!trades.length" class="tt__empty">暂无交易流水</div>
    <div v-else class="tt__scroll" :style="{ maxHeight }">
      <table class="tt__table">
        <thead>
          <tr>
            <th>时间</th>
            <th>方向</th>
            <th class="num">价格</th>
            <th class="num">数量</th>
            <th class="num">费用</th>
            <th v-if="showPos" class="num">累计持仓</th>
            <th class="num">已实现盈亏</th>
            <th>原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in rows" :key="`${r.ts}-${i}`">
            <td class="tt__time">{{ fmtTime(r.ts) }}</td>
            <td>
              <span class="tt__side" :class="r.side">{{ r.side === 'buy' ? '买' : '卖' }}</span>
            </td>
            <td class="num">{{ r.price.toFixed(2) }}</td>
            <td class="num">{{ r.shares }}</td>
            <td class="num">{{ r.fee.toFixed(2) }}</td>
            <td v-if="showPos" class="num">{{ r.cumPos }}</td>
            <td
              class="num"
              :class="r.realized_pnl == null ? '' : r.realized_pnl >= 0 ? 't-up' : 't-down'"
            >
              {{ fmtMoney(r.realized_pnl) }}
            </td>
            <td>
              <span class="tt__reason" :class="r.reason">{{ REASON_LABEL[r.reason] || r.reason }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.tt {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.tt__head {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 2px;
}
.tt__title {
  font-size: 12px;
  color: var(--text-secondary);
}
.tt__count {
  font-size: 11px;
  color: var(--text-muted);
}
.tt__toggle {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
  cursor: pointer;
}
.tt__toggle:hover { color: var(--accent); }
.tt__empty {
  padding: 12px 0;
  text-align: center;
  font-size: 11px;
  color: var(--text-muted);
}
.tt__scroll {
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 4px;
}
.tt__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.tt__table th {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 4px 6px;
  text-align: left;
  font-weight: 500;
  color: var(--text-muted);
  background: var(--bg-panel-2);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.tt__table td {
  padding: 3px 6px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.tt__table tr:last-child td { border-bottom: none; }
.tt__table .num { text-align: right; }
.tt__time { color: var(--text-secondary); }
.tt__side {
  display: inline-block;
  min-width: 18px;
  text-align: center;
  border-radius: 3px;
  font-weight: 600;
}
.tt__side.buy { color: var(--up); background: var(--up-soft); }
.tt__side.sell { color: var(--down); background: var(--down-soft); }
.tt__reason {
  padding: 0 4px;
  border-radius: 3px;
  color: var(--text-muted);
  background: var(--bg-hover);
}
.tt__reason.stop_loss { color: var(--down); }
.tt__reason.take_profit { color: var(--up); }
</style>
