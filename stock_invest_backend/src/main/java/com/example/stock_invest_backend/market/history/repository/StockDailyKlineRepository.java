package com.example.stock_invest_backend.market.history.repository;

import com.example.stock_invest_backend.market.history.dto.StockDailyKlineRecord;

import java.util.List;

public interface StockDailyKlineRepository {

    int upsertBatch(List<StockDailyKlineRecord> records);
}
