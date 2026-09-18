/**
 * G35 · 登录页左侧三卡片配置（规格书 §2.3，登录页视觉重设计的唯一依据）。
 *
 * 用户自定义入口：**换图只需替换 `src/assets/login/` 下的图片或改本文件**，不用改组件。
 * - `mode: 'image'`（当前默认）：渲染成品卡片图，见 §2.2 尺寸规则
 * - `mode: 'data'`（预留动态化）：按结构化字段渲染，未来可接真实接口
 *   （机会指数 / 自选股行情 / 回测指标）
 *
 * 顺序固定：page1（机会指数）→ page2（重点关注）→ page3（回测指标）。
 */
import page1 from '@/assets/login/page1.png'
import page2 from '@/assets/login/page2.png'
import page3 from '@/assets/login/page3.png'

/** 卡片1 数据模式字段（机会指数仪表盘） */
export interface ChanceIndexCardData {
  /** 仪表盘百分比（0~100） */
  percent: number
  title: string
  linkText: string
}

/** 卡片2 数据模式字段（重点关注自选股） */
export interface WatchlistCardData {
  title: string
  rows: Array<{
    avatarText: string
    avatarGradient: string
    name: string
    code: string
    price: string
    changePct: number
  }>
}

/** 卡片3 数据模式字段（回测指标） */
export interface BacktestCardData {
  title: string
  winRate: string
  profitLossRatio: string
  sharpe: string
  /** 原图无标签数字（疑为交易笔数/持仓数，含义待产品确认） */
  count7: string
  annualReturn: string
  /** 原图无标签数字（疑为回测天数/样本数，含义待产品确认） */
  count112: string
}

export type LoginCardConfig =
  | { id: string; mode: 'image'; imageUrl: string; alt: string }
  | { id: string; mode: 'data'; kind: 'chance-index'; data: ChanceIndexCardData }
  | { id: string; mode: 'data'; kind: 'watchlist'; data: WatchlistCardData }
  | { id: string; mode: 'data'; kind: 'backtest'; data: BacktestCardData }

export const loginCards: LoginCardConfig[] = [
  { id: 'chance-index', mode: 'image', imageUrl: page1, alt: '机会指数' },
  { id: 'watchlist', mode: 'image', imageUrl: page2, alt: '重点关注' },
  { id: 'backtest', mode: 'image', imageUrl: page3, alt: '回测指标' },
]
