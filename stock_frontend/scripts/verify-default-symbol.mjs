import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
const out=resolve('node_modules/.cache/default-symbol/check.mjs')
await mkdir(resolve(out,'..'),{recursive:true})
await build({stdin:{contents:"export {ensureDefaultSymbol} from './src/composables/useDefaultSymbol'",resolveDir:process.cwd()},outfile:out,bundle:true,format:'esm',platform:'node',plugins:[{name:'fixtures',setup(b){
  b.onResolve({filter:/^@\/(api\/market|stores\/market|stores\/user)$/},({path})=>({path,namespace:'fixture'}))
  b.onLoad({filter:/.*/,namespace:'fixture'},({path})=>({contents:path.includes('/api/')
    ? 'export const fetchSymbols=async()=>globalThis.fixture.indices;export const fetchWatchlist=async()=>{globalThis.fixture.calls++;if(globalThis.fixture.fail)throw Error("offline");return globalThis.fixture.remote}'
    :path.endsWith('/user')?'export const useUserStore=()=>globalThis.fixture.user':'export const useMarketStore=()=>globalThis.fixture.market'}))
}}]})
const {ensureDefaultSymbol}=await import(pathToFileURL(out).href)
const fixed={id:70,code:'000001',name:'上证指数',type:'index'}
function reset(token=''){
  globalThis.fixture={user:{token},calls:0,fail:false,indices:[fixed],remote:[],market:{current:null,watchlist:[],fixedIndices:[],setCurrent(s){this.current=s},setWatchlist(s){this.watchlist=s},setFixedIndices(s){this.fixedIndices=s}}}
  return globalThis.fixture
}
let f=reset();f.market.watchlist=[{symbol_id:123,code:'stale',name:'old account',type:'stock'}]
await ensureDefaultSymbol();assert.equal(f.calls,0,'guest cannot request private watchlist');assert.deepEqual(f.market.current,fixed)
f=reset('signed-in');f.remote=[{symbol_id:1,code:'600519',name:'茅台',type:'stock'}]
await ensureDefaultSymbol();assert.equal(f.calls,1);assert.equal(f.market.current.code,'600519')
f=reset('signed-in');f.fail=true
await ensureDefaultSymbol();assert.equal(f.calls,1);assert.deepEqual(f.market.current,fixed)
f=reset();f.market.current={id:1,code:'300308'}
await ensureDefaultSymbol();assert.equal(f.calls,0);assert.equal(f.market.current.code,'300308')
console.log('Default symbol: guest skips private watchlist and stale account data; authenticated priority and index fallback passed.')
