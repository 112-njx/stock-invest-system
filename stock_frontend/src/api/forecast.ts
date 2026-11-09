import { request } from './http'

export interface ForecastEvidence {
  session: string
  feature: string
  reason: string
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

export const setForecastTracking = (symbol: string, enabled: boolean) =>
  request<{ tracking: boolean }>({ url: '/forecast/tracking', method: 'put', data: { symbol, enabled }, silent: true })
