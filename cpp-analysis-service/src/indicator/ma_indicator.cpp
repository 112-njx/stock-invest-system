#include "indicator/ma_indicator.h"

#include <limits>
//该文件是用于SMA序列计算
namespace indicator {

std::vector<double> calculateSimpleMovingAverageSeries(const std::vector<double>& prices, int period) {
    std::vector<double> maSeries(prices.size(), std::numeric_limits<double>::quiet_NaN());
    if (period <= 0 || prices.empty() || prices.size() < static_cast<size_t>(period)) {
        return maSeries;
    }

    double rollingSum = 0.0;
    for (size_t i = 0; i < prices.size(); ++i) {
        rollingSum += prices[i];
        if (i >= static_cast<size_t>(period)) {
            rollingSum -= prices[i - static_cast<size_t>(period)];
        }
        if (i + 1 >= static_cast<size_t>(period)) {
            maSeries[i] = rollingSum / static_cast<double>(period);
        }
    }
    return maSeries;
}

bool isValidMaPoint(double maValue) {
    return maValue == maValue;
}

}  // namespace indicator
