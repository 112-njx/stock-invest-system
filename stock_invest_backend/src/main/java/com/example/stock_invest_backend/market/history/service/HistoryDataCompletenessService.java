package com.example.stock_invest_backend.market.history.service;

import com.example.stock_invest_backend.market.history.dto.CompletenessResult;
import com.example.stock_invest_backend.market.history.dto.StockDailyKlineRecord;
import com.example.stock_invest_backend.market.history.repository.StockDailyKlineRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.DayOfWeek;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

@Service
public class HistoryDataCompletenessService {

    private static final Logger log = LoggerFactory.getLogger(HistoryDataCompletenessService.class);
    private static final double MIN_COVERAGE = 0.95;

    private final StockDailyKlineRepository repository;

    public HistoryDataCompletenessService(StockDailyKlineRepository repository) {
        this.repository = repository;
    }

    public CompletenessResult check(String symbol, LocalDate startDate, LocalDate endDate, String adjustType) {
        if (symbol == null || symbol.isBlank()) {
            throw new IllegalArgumentException("symbol is required");
        }
        if (startDate == null || endDate == null) {
            throw new IllegalArgumentException("startDate and endDate are required");
        }
        if (endDate.isBefore(startDate)) {
            throw new IllegalArgumentException("endDate must be >= startDate");
        }
        if (startDate.until(endDate).getYears() > 10) {
            throw new IllegalArgumentException("date range must not exceed 10 years");
        }

        List<LocalDate> expectedTradingDays = enumerateTradingDays(startDate, endDate);
        List<StockDailyKlineRecord> actualRecords =
                repository.findBySymbolAndDateRange(symbol, startDate, endDate);

        Set<LocalDate> actualDates = new HashSet<>();
        for (StockDailyKlineRecord r : actualRecords) {
            actualDates.add(r.getTradeDate());
        }

        List<LocalDate> missing = new ArrayList<>();
        for (LocalDate d : expectedTradingDays) {
            if (!actualDates.contains(d)) {
                missing.add(d);
            }
        }

        List<CompletenessResult.MissingRange> ranges = compressToRanges(missing);
        int expected = expectedTradingDays.size();
        int actual = actualDates.size();
        boolean complete = expected == 0 || ((double) actual / expected) >= MIN_COVERAGE;

        CompletenessResult r = new CompletenessResult();
        r.setSymbol(symbol);
        r.setAdjustType(adjustType);
        r.setStartDate(startDate);
        r.setEndDate(endDate);
        r.setExpected(expected);
        r.setActual(actual);
        r.setComplete(complete);
        r.setMissingRanges(ranges);
        r.setMessage(String.format("expected=%d actual=%d missing=%d ranges=%d",
                expected, actual, missing.size(), ranges.size()));

        log.info("completeness symbol={} range={}~{} adjust={} expected={} actual={} missingRanges={} complete={}",
                symbol, startDate, endDate, adjustType, expected, actual, ranges.size(), complete);
        return r;
    }

    private List<LocalDate> enumerateTradingDays(LocalDate start, LocalDate end) {
        List<LocalDate> out = new ArrayList<>();
        for (LocalDate d = start; !d.isAfter(end); d = d.plusDays(1)) {
            DayOfWeek dow = d.getDayOfWeek();
            if (dow == DayOfWeek.SATURDAY || dow == DayOfWeek.SUNDAY) continue;
            if (ChineseHolidays.isHoliday(d)) continue;
            out.add(d);
        }
        return out;
    }

    private List<CompletenessResult.MissingRange> compressToRanges(List<LocalDate> missing) {
        if (missing.isEmpty()) return List.of();
        TreeSet<LocalDate> sorted = new TreeSet<>(missing);
        List<CompletenessResult.MissingRange> ranges = new ArrayList<>();
        LocalDate rangeStart = null;
        LocalDate prev = null;
        for (LocalDate d : sorted) {
            if (rangeStart == null) {
                rangeStart = d;
                prev = d;
                continue;
            }
            if (nextTradingDay(prev).equals(d)) {
                prev = d;
            } else {
                ranges.add(new CompletenessResult.MissingRange(rangeStart, prev));
                rangeStart = d;
                prev = d;
            }
        }
        ranges.add(new CompletenessResult.MissingRange(rangeStart, prev));
        return ranges;
    }

    private LocalDate nextTradingDay(LocalDate d) {
        LocalDate n = d.plusDays(1);
        while (n.getDayOfWeek() == DayOfWeek.SATURDAY
                || n.getDayOfWeek() == DayOfWeek.SUNDAY
                || ChineseHolidays.isHoliday(n)) {
            n = n.plusDays(1);
        }
        return n;
    }
}
