import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'
const {outputText}=ts.transpileModule(readFileSync(new URL('../src/utils/visibleCandleExtrema.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext}})
const {visibleCandleExtrema}=await import('data:text/javascript;base64,'+Buffer.from(outputText).toString('base64'))
let range={from:1,to:2}, labels=[]
const bars=[{time:0,high:100,low:1},{time:1,high:12.08,low:10.5},{time:2,high:11.9,low:9.99}]
const chart={timeScale:()=>({getVisibleLogicalRange:()=>range,timeToCoordinate:t=>t*40}),options:()=>({layout:{textColor:'#fff',background:{color:'#000'}}})}
const series={dataByIndex:i=>bars[i],priceToCoordinate:v=>150-v*5,priceFormatter:()=>({format:v=>v.toFixed(2)})}
const ctx={save(){},restore(){},measureText:t=>({width:t.length*6}),beginPath(){},moveTo(){},lineTo(){},stroke(){},strokeText(){},fillText:t=>labels.push(t)}
const renderer=visibleCandleExtrema(chart,series).paneViews()[0].renderer()
const target={useMediaCoordinateSpace:fn=>fn({context:ctx,mediaSize:{width:120,height:200}})}
renderer.draw(target);assert.deepEqual(labels,['12.08','9.99'])
range={from:2,to:2};labels=[];renderer.draw(target);assert.deepEqual(labels,['11.90','9.99'])
range=null;labels=[];renderer.draw(target);assert.deepEqual(labels,[])
console.log('Visible candle extrema checks passed')
