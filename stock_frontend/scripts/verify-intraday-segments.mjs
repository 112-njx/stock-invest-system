import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const source = readFileSync(new URL('../src/utils/intradaySegments.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } })
const { averageSegments } = await import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'))
const rows = [
  {date:20261105093000,average:10}, {date:20261105150000,average:11},
  {date:20261106093000,average:12}, {date:20261106093100,average:null},
  {date:20261106093200,average:13}, {date:20261106093300,average:14},
  {date:20261109093000,average:15},
]
const segments = averageSegments(rows)
assert.deepEqual(segments.map(s => s.map(r => r.date)), [
  [20261105093000,20261105150000], [20261106093000],
  [20261106093200,20261106093300], [20261109093000],
])
assert.equal(segments.flat().length, rows.filter(r => r.average !== null).length)
assert.deepEqual(averageSegments([]), [])
assert.deepEqual(averageSegments([{date:20261106093000,average:null}]), [])
console.log('Intraday segmentation checks passed')
