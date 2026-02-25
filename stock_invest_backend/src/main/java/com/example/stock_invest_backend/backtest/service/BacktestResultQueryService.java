package com.example.stock_invest_backend.backtest.service;

import com.example.stock_invest_backend.backtest.dto.BacktestResultView;
import com.example.stock_invest_backend.backtest.repository.BacktestResultRepository;
import org.springframework.stereotype.Service;

import java.util.List;

//前端查询回测结果服务
@Service
public class BacktestResultQueryService {

    private final BacktestResultRepository backtestResultRepository;

    public BacktestResultQueryService(BacktestResultRepository backtestResultRepository) {
        this.backtestResultRepository = backtestResultRepository;
    }

    public List<BacktestResultView> query(String symbol, String strategyCode, int limit) {
        if (symbol == null || symbol.isBlank()) {
            throw new IllegalArgumentException("symbol is required");
        }
        if (strategyCode == null || strategyCode.isBlank()) {
            throw new IllegalArgumentException("strategyCode is required");
        }
        if (limit <= 0) {
            throw new IllegalArgumentException("limit must be > 0");
        }
        return backtestResultRepository.findBySymbolAndStrategy(symbol, strategyCode, limit);
    }
}
