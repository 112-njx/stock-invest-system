package com.example.stock_invest_backend.lof.repository;

import java.util.List;

public interface LofSymbolRegistryRepository {

    List<LofSymbolRegistryRecord> findEnabledSymbols(int limit);

    int upsertBatch(List<LofSymbolRegistryRecord> records);
}
