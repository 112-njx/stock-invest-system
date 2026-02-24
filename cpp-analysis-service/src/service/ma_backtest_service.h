#pragma once

#include <vector>

#include "model/market_data.h"

class MaBacktestService {
public:
    MaBacktestResult runBacktest(const std::vector<DailyBar>& bars, int period) const;
};
