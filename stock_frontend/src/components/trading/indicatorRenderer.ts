import { LineSeries, HistogramSeries, LineStyle, type IPaneApi, type ISeriesApi, type IPriceLine, type UTCTimestamp } from 'lightweight-charts'
import type { IndicatorDefinition } from '@/composables/useIndicatorCatalog'
import type { IndicatorRow } from '@/api/market'
export function createIndicatorSeries(pane: IPaneApi<any>, definition: IndicatorDefinition, text: string) {
  const series: ISeriesApi<any>[] = definition.series.map(line => pane.addSeries(line.kind === 'histogram' ? HistogramSeries : LineSeries, {
    color:line.color, priceLineVisible:false, lastValueVisible:false,
    ...(definition.format === 'volume' ? {priceFormat:{type:'volume'}} : {priceFormat:{type:'price',precision:definition.precision ?? 2,minMove:10 ** -(definition.precision ?? 2)}}),
  }))
  const referenceLines: IPriceLine[] = definition.reference_lines.map(price => series[0]!.createPriceLine({price,color:text,lineWidth:1,lineStyle:LineStyle.Dashed,axisLabelVisible:false}))
  return { series, referenceLines }
}
export function fillIndicatorSeries(series: ISeriesApi<any>[], definition: IndicatorDefinition, rows: IndicatorRow[], time: (ts:string)=>UTCTimestamp, colors:{up:string;down:string}) {
  for (const [index,line] of definition.series.entries()) series[index]?.setData(rows.map(row => {
    const value = (row as unknown as Record<string, unknown>)[line.field]
    const numeric = typeof value === 'number' && Number.isFinite(value)
    return {time:time(row.ts), ...(numeric ? {value} : {}), ...(line.kind === 'histogram' ? {color: (line.direction === 'candle' ? row.close >= row.open : Number(value) >= 0) ? colors.up : colors.down} : {})}
  }))
}
