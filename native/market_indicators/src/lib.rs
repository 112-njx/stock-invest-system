use pyo3::{exceptions::PyValueError, prelude::*};
use serde::{Deserialize, Serialize};
use std::collections::VecDeque;

const VERSION: u32 = 1;
const WINDOW: usize = 20;
const PIVOT_LOOKBACK: usize = 40;

#[derive(Clone, Copy, Deserialize, Serialize)]
struct Bar {
    day: i32,
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    volume: f64,
}

type InputBar = (i32, f64, f64, f64, f64, f64);

impl From<InputBar> for Bar {
    fn from((day, open, high, low, close, volume): InputBar) -> Self {
        Self {
            day,
            open,
            high,
            low,
            close,
            volume,
        }
    }
}

impl Bar {
    fn valid(&self) -> bool {
        [self.open, self.high, self.low, self.close, self.volume]
            .iter()
            .all(|v| v.is_finite())
            && self.low <= self.open.min(self.close)
            && self.high >= self.open.max(self.close)
            && self.volume >= 0.0
    }
}

#[derive(Default, Deserialize, Serialize)]
struct Average {
    warmup_sum: f64,
    value: Option<f64>,
}

impl Average {
    fn append(&mut self, sample: f64, count: usize, period: usize, alpha: f64) -> Option<f64> {
        if let Some(last) = self.value {
            self.value = Some(sample * alpha + last * (1.0 - alpha));
        } else {
            self.warmup_sum += sample;
            if count == period {
                self.value = Some(self.warmup_sum / period as f64);
                self.warmup_sum = 0.0;
            }
        }
        self.value
    }
}

#[derive(Clone, Copy, Deserialize, Serialize)]
struct Pivot {
    day: i32,
    bar_number: usize,
    price: f64,
    kind: PivotKind,
}

#[derive(Clone, Copy, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum PivotKind {
    High,
    Low,
}

#[derive(Default, Deserialize, Serialize)]
struct State {
    count: usize,
    ema: Average,
    atr: Average,
    recent: VecDeque<Bar>,
    pivots: VecDeque<Pivot>,
}

#[derive(Serialize)]
struct Features {
    ema20: Option<f64>,
    atr14: Option<f64>,
    true_range: f64,
    volume_ratio20: Option<f64>,
    body_ratio: Option<f64>,
    upper_wick_ratio: Option<f64>,
    lower_wick_ratio: Option<f64>,
    close_position: Option<f64>,
    range_atr_ratio: Option<f64>,
    overlap_ratio: Option<f64>,
    inside_bar: bool,
    outside_bar: bool,
    breakout20: Option<&'static str>,
    confirmed_pivots: Vec<Pivot>,
    support: Option<f64>,
    resistance: Option<f64>,
    pullback: Option<Pullback>,
}

#[derive(Serialize)]
struct Pullback {
    direction: &'static str,
    from_day: i32,
    swing_fraction: f64,
    depth_atr: Option<f64>,
}

fn ratio(numerator: f64, denominator: f64) -> Option<f64> {
    (denominator > 0.0).then(|| numerator / denominator)
}

impl State {
    fn append(&mut self, bar: Bar) -> PyResult<Features> {
        let previous = self.recent.back().copied();
        if !bar.valid() || previous.is_some_and(|prev| bar.day <= prev.day) {
            return Err(PyValueError::new_err("invalid or unordered daily candle"));
        }
        self.count += 1;
        let range = bar.high - bar.low;
        let tr = previous.map_or(range, |prev| {
            range
                .max((bar.high - prev.close).abs())
                .max((bar.low - prev.close).abs())
        });
        let ema20 = self.ema.append(bar.close, self.count, 20, 2.0 / 21.0);
        let atr14 = self.atr.append(tr, self.count, 14, 1.0 / 14.0);
        let volume_ratio20 = (self.recent.len() == WINDOW)
            .then(|| self.recent.iter().map(|row| row.volume).sum::<f64>() / WINDOW as f64)
            .and_then(|average| ratio(bar.volume, average));
        let breakout20 = (self.recent.len() == WINDOW).then(|| {
            let high = self
                .recent
                .iter()
                .map(|row| row.high)
                .fold(f64::NEG_INFINITY, f64::max);
            let low = self
                .recent
                .iter()
                .map(|row| row.low)
                .fold(f64::INFINITY, f64::min);
            match (
                bar.close > high,
                bar.close < low,
                bar.high > high,
                bar.low < low,
            ) {
                (true, _, _, _) => "close_up",
                (_, true, _, _) => "close_down",
                (_, _, true, true) => "wick_both",
                (_, _, true, false) => "wick_up",
                (_, _, false, true) => "wick_down",
                _ => "none",
            }
        });
        let overlap_ratio = previous.and_then(|prev| {
            let overlap = (bar.high.min(prev.high) - bar.low.max(prev.low)).max(0.0);
            ratio(overlap, range.min(prev.high - prev.low))
        });
        let mut confirmed_pivots = Vec::new();
        if let (Some(left), Some(middle)) = (self.recent.iter().rev().nth(1), previous) {
            // The middle candle becomes a pivot only when the right candle closes.
            for (kind, confirmed, price) in [
                (
                    PivotKind::High,
                    middle.high > left.high && middle.high > bar.high,
                    middle.high,
                ),
                (
                    PivotKind::Low,
                    middle.low < left.low && middle.low < bar.low,
                    middle.low,
                ),
            ] {
                if confirmed {
                    confirmed_pivots.push(Pivot {
                        day: middle.day,
                        bar_number: self.count - 1,
                        price,
                        kind,
                    });
                }
            }
        }
        self.pivots.extend(confirmed_pivots.iter().copied());
        self.pivots
            .retain(|pivot| self.count - pivot.bar_number < PIVOT_LOOKBACK);
        let support = self
            .pivots
            .iter()
            .filter(|p| p.kind == PivotKind::Low && p.price <= bar.close)
            .map(|p| p.price)
            .reduce(f64::max);
        let resistance = self
            .pivots
            .iter()
            .filter(|p| p.kind == PivotKind::High && p.price >= bar.close)
            .map(|p| p.price)
            .reduce(f64::min);
        let pullback = self.pullback(bar, atr14);
        self.recent.push_back(bar);
        if self.recent.len() > WINDOW {
            self.recent.pop_front();
        }
        Ok(Features {
            ema20,
            atr14,
            true_range: tr,
            volume_ratio20,
            body_ratio: ratio((bar.close - bar.open).abs(), range),
            upper_wick_ratio: ratio(bar.high - bar.open.max(bar.close), range),
            lower_wick_ratio: ratio(bar.open.min(bar.close) - bar.low, range),
            close_position: ratio(bar.close - bar.low, range),
            range_atr_ratio: atr14.and_then(|atr| ratio(range, atr)),
            overlap_ratio,
            inside_bar: previous.is_some_and(|p| {
                bar.high <= p.high && bar.low >= p.low && (bar.high < p.high || bar.low > p.low)
            }),
            outside_bar: previous.is_some_and(|p| {
                bar.high >= p.high && bar.low <= p.low && (bar.high > p.high || bar.low < p.low)
            }),
            breakout20,
            confirmed_pivots,
            support,
            resistance,
            pullback,
        })
    }

    fn pullback(&self, bar: Bar, atr: Option<f64>) -> Option<Pullback> {
        let latest = self.pivots.back()?;
        if self
            .pivots
            .iter()
            .rev()
            .nth(1)
            .is_some_and(|p| p.day == latest.day)
        {
            return None; // An outside bar can confirm both sides with no known ordering.
        }
        let anchor = self
            .pivots
            .iter()
            .rev()
            .find(|p| p.kind != latest.kind && p.day < latest.day)?;
        let (direction, leg, depth) = match latest.kind {
            PivotKind::High => ("up", latest.price - anchor.price, latest.price - bar.close),
            PivotKind::Low => (
                "down",
                anchor.price - latest.price,
                bar.close - latest.price,
            ),
        };
        let depth = depth.max(0.0);
        Some(Pullback {
            direction,
            from_day: latest.day,
            swing_fraction: ratio(depth, leg)?,
            depth_atr: atr.and_then(|atr| ratio(depth, atr)),
        })
    }
}

#[derive(Deserialize, Serialize)]
struct Checkpoint {
    version: u32,
    state: State,
}

#[pyfunction]
#[pyo3(signature = (bars, checkpoint=None))]
fn calculate(
    py: Python<'_>,
    bars: Vec<InputBar>,
    checkpoint: Option<&str>,
) -> PyResult<(String, String)> {
    let mut state = match checkpoint {
        Some(raw) => {
            let saved: Checkpoint = serde_json::from_str(raw)
                .map_err(|_| PyValueError::new_err("invalid indicator checkpoint"))?;
            if saved.version != VERSION
                || saved.state.recent.len() != saved.state.count.min(WINDOW)
                || saved
                    .state
                    .pivots
                    .iter()
                    .any(|p| p.bar_number >= saved.state.count)
            {
                return Err(PyValueError::new_err("incompatible indicator checkpoint"));
            }
            saved.state
        }
        None => State::default(),
    };
    py.detach(move || {
        let features = bars
            .into_iter()
            .map(|bar| state.append(bar.into()))
            .collect::<PyResult<Vec<_>>>()?;
        let rows = serde_json::to_string(&features)
            .map_err(|err| PyValueError::new_err(err.to_string()))?;
        let checkpoint = serde_json::to_string(&Checkpoint {
            version: VERSION,
            state,
        })
        .map_err(|err| PyValueError::new_err(err.to_string()))?;
        Ok((rows, checkpoint))
    })
}

#[pymodule]
fn market_indicators(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add("FEATURE_VERSION", VERSION)?;
    module.add_function(wrap_pyfunction!(calculate, module)?)?;
    Ok(())
}
