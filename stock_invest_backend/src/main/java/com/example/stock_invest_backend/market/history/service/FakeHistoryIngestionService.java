package com.example.stock_invest_backend.market.history.service;

import com.example.stock_invest_backend.market.history.config.HistoryIngestionProperties;
import com.example.stock_invest_backend.market.history.dto.StockDailyKlineRecord;
import com.example.stock_invest_backend.market.history.repository.StockDailyKlineRepository;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;

@Service
public class FakeHistoryIngestionService {

    private final StockDailyKlineRepository repository;
    private final HistoryIngestionProperties ingestionProperties;

    public FakeHistoryIngestionService(StockDailyKlineRepository repository,
                                       HistoryIngestionProperties ingestionProperties) {
        this.repository = repository;
        this.ingestionProperties = ingestionProperties;
    }

    @Scheduled(cron = "${market.history.ingestion.cron:0 15 16 * * MON-FRI}")
    public void scheduledIngest() {
        if (!ingestionProperties.isEnabled()) {
            return;
        }
        ingest(ingestionProperties.getDefaultSymbols(), ingestionProperties.getMonths());
    }

    public int ingest(List<String> symbols, int months) {
        List<StockDailyKlineRecord> records = buildFakeRecords(symbols, months);
        return repository.upsertBatch(records);
    }

    private List<StockDailyKlineRecord> buildFakeRecords(List<String> symbols, int months) {
        List<StockDailyKlineRecord> result = new ArrayList<>();
        LocalDate end = LocalDate.now();
        LocalDate start = end.minusMonths(Math.max(months, 1));

        for (String symbol : symbols) {
            if (!StringUtils.hasText(symbol)) {
                continue;
            }
            BigDecimal base = BigDecimal.valueOf(10 + Math.abs(symbol.hashCode() % 5000) / 100.0)
                    .setScale(2, RoundingMode.HALF_UP);

            for (LocalDate date = start; !date.isAfter(end); date = date.plusDays(1)) {
                if (date.getDayOfWeek() == DayOfWeek.SATURDAY || date.getDayOfWeek() == DayOfWeek.SUNDAY) {
                    continue;
                }

                BigDecimal drift = BigDecimal.valueOf(ThreadLocalRandom.current().nextDouble(-0.6, 0.6));
                BigDecimal open = base.add(drift).setScale(2, RoundingMode.HALF_UP);
                BigDecimal close = open.add(BigDecimal.valueOf(ThreadLocalRandom.current().nextDouble(-0.5, 0.5)))
                        .setScale(2, RoundingMode.HALF_UP);
                BigDecimal high = open.max(close).add(BigDecimal.valueOf(0.3)).setScale(2, RoundingMode.HALF_UP);
                BigDecimal low = open.min(close).subtract(BigDecimal.valueOf(0.3)).max(BigDecimal.ZERO)
                        .setScale(2, RoundingMode.HALF_UP);

                StockDailyKlineRecord record = new StockDailyKlineRecord();
                record.setSymbol(symbol.toLowerCase());
                record.setTradeDate(date);
                record.setOpenPrice(open);
                record.setHighPrice(high);
                record.setLowPrice(low);
                record.setClosePrice(close);
                long volume = ThreadLocalRandom.current().nextLong(100_000, 10_000_000);
                record.setVolume(volume);
                record.setTurnover(close.multiply(BigDecimal.valueOf(volume)).setScale(2, RoundingMode.HALF_UP));
                record.setSource("mock-ingestion");
                result.add(record);

                base = close;
            }
        }

        return result;
    }
}
