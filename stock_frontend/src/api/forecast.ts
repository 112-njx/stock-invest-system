import { request } from './http'

export interface ForecastEvidence {
  session: string
  feature: string
  value: unknown
}

export interface ForecastRun {
  id: number
  symbol: string
  trigger: 'manual' | 'auto'
  status: 'queued' | 'diagnosing' | 'predicting' | 'completed' | 'failed'
  created_at: string
  snapshot: {
    latest_session: string | null
    as_of: string
    bar_count: number
    data_version: string | null
    feature_version: number
    source: 'stockdb' | 'akshare' | null
  }
  diagnosis: { regime: string; bias: string; summary: string; evidence: ForecastEvidence[] } | null
  prediction: {
    next_candle: { direction: string; reason: string; evidence: ForecastEvidence[] }
    next_regime: { regime: string; reason: string; evidence: ForecastEvidence[] }
  } | null
  models: {
    diagnosis?: { name: string; revision: string | null }
    prediction?: { name: string; revision: string | null }
  }
  error: string | null
}

export const getForecastHistory = (symbol: string) =>
  request<{ runs: ForecastRun[]; tracking: boolean }>({ url: '/forecast/runs', params: { symbol }, silent: true })

export const startForecast = (symbol: string) =>
  request<ForecastRun>({ url: '/forecast/runs', method: 'post', data: { symbol }, timeout: 60000, silent: true })

export const retryForecast = (id: number) =>
  request<ForecastRun>({ url: `/forecast/runs/${id}/retry`, method: 'post', silent: true })

export const setForecastTracking = (symbol: string, enabled: boolean) =>
  request<{ tracking: boolean }>({ url: '/forecast/tracking', method: 'put', data: { symbol, enabled }, silent: true })

export interface ReplayOptions {
  end: string | null
  samples: number
  mode: 'reconstructed' | 'archived'
}

export interface ReplayScore {
  labelled: number
  covered: number
  hits: number
}

export interface ForecastReplay {
  id: number
  status: 'queued' | 'running' | 'completed' | 'failed'
  error: string | null
  options: ReplayOptions
  report: {
    total: number
    horizon: number
    rule_version: number
    scores: Record<string, ReplayScore>
    cases: {
      session: string
      next_session: string | null
      regime_through: string | null
      direction?: string
      regime?: string
      actual_direction: string | null
      actual_regime: string | null
      last_candle: string
      always_up: string
      previous_regime: string | null
      status: string
    }[]
  } | null
}

export const getForecastReplay = (symbol: string) =>
  request<ForecastReplay | null>({ url: '/forecast/replay', params: { symbol }, silent: true })

export const startForecastReplay = (symbol: string, options: ReplayOptions) =>
  request<ForecastReplay>({ url: '/forecast/replay', method: 'post', data: { symbol, ...options }, silent: true })
