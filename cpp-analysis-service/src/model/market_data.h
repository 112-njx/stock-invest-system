#pragma once

#include <string>
#include <vector>

struct DailyBar {
    std::string tradeDate;
    double openPrice;
    double highPrice;
    double lowPrice;
    double closePrice;
};

enum class MaSignalType {
    CrossUp,
    CrossDown
};

struct MaSignal {
    std::string tradeDate;
    MaSignalType type;
    double closePrice;
    double maValue;
};

struct MaBacktestResult {
    int totalSignals = 0;
    int winSignals = 0;
    double successRate = 0.0;
    std::vector<MaSignal> signals;
};
