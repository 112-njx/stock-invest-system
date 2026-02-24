#include "service/ma_backtest_service.h"

#include "indicator/ma_indicator.h"

//该文件 上穿/下破识别、胜率统计
MaBacktestResult MaBacktestService::runBacktest(const std::vector<DailyBar>& bars, int period) const {
    MaBacktestResult result;
    if (period <= 0 || bars.empty()) {
        return result;
    }

    std::vector<double> closePrices;
    closePrices.reserve(bars.size());
    for (const DailyBar& bar : bars) {
        closePrices.push_back(bar.closePrice);
    }

    const std::vector<double> maSeries = indicator::calculateSimpleMovingAverageSeries(closePrices, period);

    for (size_t i = 1; i < bars.size(); ++i) {
        if (!indicator::isValidMaPoint(maSeries[i - 1]) || !indicator::isValidMaPoint(maSeries[i])) {
            continue;
        }

        const double previousDiff = closePrices[i - 1] - maSeries[i - 1];
        const double currentDiff = closePrices[i] - maSeries[i];
        if (previousDiff <= 0.0 && currentDiff > 0.0) {
            result.signals.push_back(
                MaSignal{bars[i].tradeDate, MaSignalType::CrossUp, closePrices[i], maSeries[i]});
        } else if (previousDiff >= 0.0 && currentDiff < 0.0) {
            result.signals.push_back(
                MaSignal{bars[i].tradeDate, MaSignalType::CrossDown, closePrices[i], maSeries[i]});
        }
    }

    std::vector<size_t> buySignalIndexes;
    for (size_t i = 0; i < result.signals.size(); ++i) {
        if (result.signals[i].type == MaSignalType::CrossUp) {
            buySignalIndexes.push_back(i);
        }
    }

    result.totalSignals = static_cast<int>(buySignalIndexes.size());
    for (size_t buyIndex : buySignalIndexes) {
        const MaSignal& buySignal = result.signals[buyIndex];

        // Exit at the next cross-down signal, or use the last close as open-position fallback.
        double exitPrice = closePrices.back();
        for (size_t next = buyIndex + 1; next < result.signals.size(); ++next) {
            if (result.signals[next].type == MaSignalType::CrossDown) {
                exitPrice = result.signals[next].closePrice;
                break;
            }
        }

        if (exitPrice > buySignal.closePrice) {
            result.winSignals++;
        }
    }

    if (result.totalSignals > 0) {
        result.successRate =
            static_cast<double>(result.winSignals) / static_cast<double>(result.totalSignals);
    }
    return result;
}
