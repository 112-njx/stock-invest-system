import type { IChartApi, ISeriesApi, ISeriesPrimitive, Time } from 'lightweight-charts'

/** Render with the chart itself so panning, scaling and pane resizing stay in sync. */
export function visibleCandleExtrema(chart: IChartApi, series: ISeriesApi<'Candlestick'>): ISeriesPrimitive<Time> {
  return {
    paneViews: () => [{
      zOrder: () => 'top',
      renderer: () => ({
        draw(target) {
          const range = chart.timeScale().getVisibleLogicalRange()
          if (!range) return
          target.useMediaCoordinateSpace(({ context: ctx, mediaSize: size }) => {
            let highest: { x: number; value: number } | undefined
            let lowest: { x: number; value: number } | undefined
            for (let i = Math.ceil(range.from); i <= Math.floor(range.to); i++) {
              const bar = series.dataByIndex(i)
              if (!bar || !('high' in bar)) continue
              const x = chart.timeScale().timeToCoordinate(bar.time)
              if (x == null || x < 0 || x > size.width) continue
              if (!highest || bar.high > highest.value) highest = { x, value: bar.high }
              if (!lowest || bar.low < lowest.value) lowest = { x, value: bar.low }
            }
            ctx.save()
            const color = chart.options().layout.textColor
            ctx.font = '12px Arial, Microsoft YaHei, sans-serif'
            ctx.textAlign = 'center'
            ctx.textBaseline = 'middle'
            for (const [point, direction] of [[highest, -1], [lowest, 1]] as const) {
              if (!point) continue
              const y = series.priceToCoordinate(point.value)
              if (y == null || y < 0 || y > size.height) continue
              const text = series.priceFormatter().format(point.value)
              const half = ctx.measureText(text).width / 2 + 4
              const tx = Math.max(half, Math.min(size.width - half, point.x))
              const ty = Math.max(9, Math.min(size.height - 9, y + direction * 19))
              ctx.strokeStyle = color
              ctx.lineWidth = 1
              ctx.beginPath(); ctx.moveTo(point.x, y); ctx.lineTo(point.x, y + direction * 8); ctx.lineTo(tx, ty - direction * 7); ctx.stroke()
              // An outline keeps labels legible against candles and moving averages.
              const background = chart.options().layout.background
              ctx.strokeStyle = 'color' in background ? background.color : '#111827'
              ctx.lineWidth = 3
              ctx.strokeText(text, tx, ty)
              ctx.fillStyle = color
              ctx.fillText(text, tx, ty)
            }
            ctx.restore()
          })
        },
      }),
    }],
  }
}
