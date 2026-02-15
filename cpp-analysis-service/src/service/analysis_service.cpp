#include <vector>
using namespace std;
//这里是业务逻辑编排层
//负责业务流程，指标组合，批量计算和策略入口
#include "analysis_service.h"

double calculate_ma(const std::vector<double>& prices, int period) {
    if (period <= 0 || prices.size() < static_cast<size_t>(period))
        return 0.0;

    double sum = 0.0;
    for (size_t i = prices.size() - period; i < prices.size(); ++i) {
        sum += prices[i];
    }
    return sum / period;
}