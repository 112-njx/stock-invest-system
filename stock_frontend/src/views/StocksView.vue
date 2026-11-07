<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { request } from '@/api/http'
import { addWatchlist } from '@/api/market'
import { indexStocks, filterStocks, type IndexedStock } from '@/utils/stockSearch'
import { useMarketStore } from '@/stores/market'
import { useUserStore } from '@/stores/user'
import { useWsStore } from '@/stores/wsStore'
import { useAuthModalStore } from '@/stores/authModal'
import { toast } from '@/utils/toast'
type Row={code:string;name:string;market:'SSE'|'SZSE'|'BSE';industry:string;data_date:number;[key:string]:number|string|null}
type Col={key:string;label:string;width:number;kind?:string;signed?:boolean;hint?:string}
const columns:Col[]=[
{key:'code',label:'代码',width:85},{key:'name',label:'名称',width:110},
{key:'close',label:'最新收盘价',width:100},{key:'change',label:'涨跌额',width:85,signed:true},
{key:'change_pct',label:'涨跌幅',width:90,kind:'pct',signed:true},
{key:'volume',label:'成交量（股）',width:115,kind:'large'},{key:'amount',label:'成交额',width:110,kind:'large'},
{key:'turnover',label:'换手率',width:85,kind:'pct'},{key:'vol_ratio',label:'量比',width:75},
{key:'amplitude',label:'振幅',width:80,kind:'pct'},
...(['total_mv','float_mv','total_share','float_share'] as const).map((key,i)=>({key,label:['总市值','流通市值','总股本','流通股本'][i]!,width:115,kind:'large'})),
{key:'pe_ttm',label:'PE TTM',width:90},{key:'pb',label:'市净率 PB',width:95},
{key:'industry',label:'申万一级',width:110},
...(['open','high','low'] as const).map((key,i)=>({key,label:['今开','最高','最低'][i]!,width:85})),
...[5,10,20].map(n=>({key:`return_${n}`,label:`${n}日涨幅`,width:100,kind:'pct',signed:true})),
{key:'return_ytd',label:'年初至今涨幅',width:130,kind:'pct',signed:true,hint:'复权收益；年内上市以上市首日收盘价为基准'}].map(c=>({...c,width:c.key==='code'?100:c.key==='name'?130:Math.max(c.width+10,100)}))
const router=useRouter(),market=useMarketStore(),user=useUserStore(),ws=useWsStore(),auth=useAuthModalStore()
const rows=ref<Row[]>([]),indexed=ref<IndexedStock[]>([]),industries=ref<string[]>([]),query=ref(''),exchanges=ref<string[]>([]),industry=ref('')
const op=ref('gt'),value=ref(''),upper=ref(''),sortKey=ref('code'),asc=ref(true),date=ref(''),error=ref(''),loading=ref(false),refreshing=ref(false)
const viewport=ref<HTMLElement>(),top=ref(0),height=ref(600),active=ref(''),adding=ref(false)
const menu=ref<{row:Row;x:number;y:number}>()
let observer:ResizeObserver|undefined,timer:ReturnType<typeof setTimeout>|undefined,alive=true
const invalid=computed(()=>value.value!==''&&(!Number.isFinite(Number(value.value))||(op.value==='range'&&(upper.value===''||!Number.isFinite(Number(upper.value))||Number(upper.value)<Number(value.value)))))
const filtered=computed(()=>{
 const matches=new Set(filterStocks(indexed.value,query.value).map(s=>s.code))
 return rows.value.filter(r=>{
  if(!matches.has(r.code)||(exchanges.value.length&&!exchanges.value.includes(r.market))||(industry.value&&r.industry!==industry.value))return false
  if(value.value===''||invalid.value)return true
  const n=Number(value.value),v=r.change_pct
  if(typeof v!=='number')return false
  return op.value==='gt'?v>n:op.value==='gte'?v>=n:op.value==='lt'?v<n:op.value==='lte'?v<=n:v>=n&&v<=Number(upper.value)
 }).sort((a,b)=>{const x=a[sortKey.value],y=b[sortKey.value];if(x==null)return y==null?a.code.localeCompare(b.code):1;if(y==null)return -1;return (typeof x==='number'&&typeof y==='number'?x-y:String(x).localeCompare(String(y),'zh-CN'))*(asc.value?1:-1)||a.code.localeCompare(b.code)})
})
const rowHeight=34
const start=computed(()=>Math.max(0,Math.min(Math.floor(top.value/rowHeight)-5,filtered.value.length-1)))
const visible=computed(()=>filtered.value.slice(start.value,start.value+Math.ceil(height.value/rowHeight)+12))
const width=columns.reduce((n,c)=>n+c.width,48)
function resetScroll(){top.value=0;if(viewport.value)viewport.value.scrollTop=0;menu.value=undefined}
function reset(){query.value='';exchanges.value=[];industry.value='';value.value='';upper.value='';resetScroll()}
function sort(key:string){if(sortKey.value===key)asc.value=!asc.value;else{sortKey.value=key;asc.value=key==='code'||key==='name'}resetScroll()}
function format(r:Row,c:Col){const v=r[c.key];if(v==null)return '—';if(typeof v!=='number')return v;if(c.kind==='large')return Math.abs(v)>=1e8?(v/1e8).toFixed(2)+'亿':Math.abs(v)>=1e4?(v/1e4).toFixed(2)+'万':v.toLocaleString('zh-CN');return (c.signed&&v>0?'+':'')+v.toFixed(2)+(c.kind==='pct'?'%':'')}
function context(event:MouseEvent,row:Row){event.preventDefault();active.value=row.code;menu.value={row,x:Math.max(4,Math.min(event.clientX,innerWidth-216)),y:Math.max(4,Math.min(event.clientY,innerHeight-114))}}
function keyboardMenu(event:KeyboardEvent,row:Row){const rect=(event.currentTarget as HTMLElement).getBoundingClientRect();event.preventDefault();menu.value={row,x:Math.max(4,rect.left+80),y:Math.max(4,Math.min(rect.top,innerHeight-114))}}
function outside(e:PointerEvent){if(!(e.target as HTMLElement).closest('.stock-context'))menu.value=undefined}
function escape(e:KeyboardEvent){if(e.key==='Escape')menu.value=undefined}
function detail(row:Row){menu.value=undefined;void router.push({path:'/market/detail',query:{symbol:row.code,asset_type:'stock'}})}
async function follow(row:Row){menu.value=undefined;if(!user.token){auth.show();return}if(adding.value)return;if(market.watchlist.some(s=>s.code===row.code&&s.type==='stock')){toast.success('该股票已在关注列表');return}adding.value=true;try{const item=await addWatchlist(`stock:${row.code}`);market.addWatchlistItem(item);ws.syncSubscriptions();toast.success(`已关注 ${row.name}`)}catch{toast.error('加入关注失败，请重试')}finally{adding.value=false}}
async function load(){if(loading.value)return;loading.value=true;try{const p=await request<{items:Row[];industries:string[];date?:number;loading:boolean;refreshing?:boolean;error?:string}>({url:'/stockdb/equities',silent:true,timeout:60000});if(!alive)return;if(!p.loading){rows.value=p.items;industries.value=p.industries;date.value=String(p.date??'');indexed.value=indexStocks(p.items.map((r,i)=>({code:r.code,name:r.name,market:r.market,type:'stock',latest_date:String(r.data_date),ordinal:i})))}refreshing.value=p.loading||!!p.refreshing;error.value=p.error??''}catch(e){if(alive)error.value=e instanceof Error?e.message:'读取失败，请重试'}finally{loading.value=false;if(alive)timer=setTimeout(()=>void load(),refreshing.value?2000:60000)}}
function refresh(){clearTimeout(timer);void load()}
onMounted(()=>{observer=new ResizeObserver(entries=>{height.value=entries[0]?.contentRect.height??600});if(viewport.value)observer.observe(viewport.value);document.addEventListener('pointerdown',outside);window.addEventListener('keydown',escape);void load()})
onBeforeUnmount(()=>{alive=false;clearTimeout(timer);observer?.disconnect();document.removeEventListener('pointerdown',outside);window.removeEventListener('keydown',escape)})
</script>
<template>
<section class="stocks-page">
 <header><h1>股票</h1><span>A股 · 本地最新数据 {{ date }} · {{ filtered.length }} / {{ rows.length }} 只</span><span v-if="refreshing">正在更新数据…</span><button :disabled="loading" @click="refresh">刷新</button></header>
 <div class="filters">
 <input v-model="query" aria-label="搜索股票" placeholder="代码 / 名称 / 拼音" @input="resetScroll" />
 <fieldset><legend class="sr-only">交易所</legend><label v-for="m in [['SSE','沪市'],['SZSE','深市'],['BSE','京市']]" :key="m[0]"><input v-model="exchanges" type="checkbox" :value="m[0]" @change="resetScroll"/>{{ m[1] }}</label></fieldset>
 <select v-model="industry" aria-label="申万一级行业" @change="resetScroll"><option value="">全部行业</option><option v-for="s in industries" :key="s">{{ s }}</option></select>
 <label class="condition">涨跌幅 <select v-model="op" aria-label="涨跌幅条件" @change="resetScroll"><option value="gt">大于</option><option value="gte">大于等于</option><option value="lt">小于</option><option value="lte">小于等于</option><option value="range">区间</option></select><input v-model="value" type="number" step="any" aria-label="涨跌幅数值" placeholder="不限" @input="resetScroll"/>%<template v-if="op==='range'"> 至 <input v-model="upper" type="number" step="any" aria-label="涨跌幅上限" @input="resetScroll"/>%</template></label>
 <button @click="reset">重置</button><span class="hint">右键股票行：加入关注 / 查看详细数据</span>
 </div>
 <p v-if="invalid||error" role="status">{{ invalid?'请输入有效区间，下限须不大于上限':error }}</p>
 <div ref="viewport" class="table-wrap" @scroll="top=($event.target as HTMLElement).scrollTop;menu=undefined">
 <table :style="{width:`${width}px`}"><colgroup><col style="width:48px"/><col v-for="c in columns" :key="c.key" :style="{width:`${c.width}px`}"/></colgroup>
 <thead><tr><th>序号</th><th v-for="c in columns" :key="c.key" :class="[c.key,{fixed:c.key==='code'||c.key==='name'}]" :title="c.hint" :aria-sort="sortKey===c.key?(asc?'ascending':'descending'):'none'"><button @click="sort(c.key)">{{ c.label }} {{ sortKey===c.key?(asc?'↑':'↓'):'' }}</button></th></tr></thead>
 <tbody><tr v-if="start" aria-hidden="true"><td :colspan="columns.length+1" :style="{height:`${start*rowHeight}px`,padding:0}"/></tr>
 <tr v-for="(r,i) in visible" :key="r.code" tabindex="0" :class="{selected:active===r.code}" :aria-label="`${r.code} ${r.name}`" @click="active=r.code" @dblclick="detail(r)" @contextmenu="context($event,r)" @keydown.enter="detail(r)" @keydown.shift.f10="keyboardMenu($event,r)">
 <td class="ordinal">{{ start+i+1 }}</td><td v-for="c in columns" :key="c.key" :class="[c.key,{fixed:c.key==='code'||c.key==='name',up:(c.signed&&Number(r[c.key])>0)||(c.key==='close'&&Number(r.change_pct)>0)||(c.key==='vol_ratio'&&Number(r.vol_ratio)>1),down:(c.signed&&Number(r[c.key])<0)||(c.key==='close'&&Number(r.change_pct)<0)||(c.key==='vol_ratio'&&r.vol_ratio!=null&&Number(r.vol_ratio)<1),'high-ratio':c.key==='vol_ratio'&&Number(r.vol_ratio)>=4}]" :title="`${c.hint?c.hint+'；':''}${r[c.key]??'未提供'}${c.key==='name'?'；行情日期 '+r.data_date:''}`">{{ format(r,c) }}</td>
 </tr><tr v-if="filtered.length>start+visible.length" aria-hidden="true"><td :colspan="columns.length+1" :style="{height:`${(filtered.length-start-visible.length)*rowHeight}px`,padding:0}"/></tr></tbody></table>
 <div v-if="!filtered.length" class="empty" role="status">{{ loading||refreshing?'正在准备本地股票数据…':error||'没有符合条件的股票' }}</div>
 </div>
 <div v-if="menu" class="stock-context" role="menu" :style="{left:`${menu.x}px`,top:`${menu.y}px`}"><button role="menuitem" @click="follow(menu.row)">加入关注</button><button role="menuitem" @click="detail(menu.row)">查看详细数据</button></div>
</section>
</template>
<style scoped>
.stocks-page{--quote-highlight:#e5e65b;--quote-up:#ff3535;--quote-down:#00cf4a;--quote-ratio:#f044e8;--quote-selected:#294c70}
:global([data-theme='light'] .stocks-page){--quote-highlight:#806600;--quote-up:#cf202f;--quote-down:#008740;--quote-ratio:#a520a0;--quote-selected:#d8e8fa}
.high-ratio{color:var(--quote-ratio)!important}

.stocks-page{flex:1;min-height:0;display:flex;flex-direction:column;background:var(--bg-panel);color:var(--text);padding:10px 12px 0;gap:8px;font-family:Arial,'Microsoft YaHei','PingFang SC',sans-serif;font-size:15px;font-weight:400}header{display:flex;align-items:center;gap:14px;flex-wrap:wrap}h1{font-size:20px;margin:0}header span,.hint{color:var(--text-secondary)}header>button{margin-left:auto}.filters{display:flex;align-items:center;gap:10px;flex-wrap:wrap}input,select,button{font:inherit;color:var(--text);background:var(--bg-panel);border:1px solid var(--border);border-radius:3px;padding:5px 8px}button{cursor:pointer}button:hover{background:var(--bg-hover)}fieldset{display:flex;gap:8px;border:0;margin:0;padding:0}fieldset label,.condition{display:flex;align-items:center;gap:4px}.condition input{width:88px}.table-wrap{position:relative;flex:1;min-height:0;overflow:auto;border:1px solid var(--border)}table{table-layout:fixed;border-collapse:separate;border-spacing:0;font-variant-numeric:tabular-nums;text-align:right}th{position:sticky;top:0;z-index:3;height:36px;background:var(--bg-panel);border-bottom:1px solid var(--border);font-weight:400;color:var(--text-secondary)}th button{color:var(--text-secondary);border:0;width:100%;text-align:right;white-space:nowrap;padding:0 6px;border-radius:0}td{height:34px;padding:0 7px;border-bottom:1px solid var(--border);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.ordinal{color:var(--text);text-align:center}.fixed{position:sticky;background:var(--bg-panel);z-index:1}.code{left:0;text-align:left}.name{left:100px;text-align:left;border-right:1px solid var(--border)}th.fixed{z-index:4}td.code,td.name,td.volume,td.amount,td.total_mv{color:var(--quote-highlight)}.industry{text-align:left}.selected td{background:var(--quote-selected)}tbody tr:hover td{background:var(--bg-hover)}.up{color:var(--quote-up)}.down{color:var(--quote-down)}.stock-context{position:fixed;z-index:1000;width:210px;padding:4px;background:var(--bg-panel);border:1px solid var(--border);box-shadow:0 5px 18px #0004}.stock-context button{display:block;width:100%;border:0;text-align:left;padding:10px 16px}.empty{position:sticky;left:0;padding:40px;color:var(--text-secondary)}p{margin:0;color:var(--text-secondary)}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}
</style>
