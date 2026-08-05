package com.example.stock_invest_backend.market.history.service;

import com.example.stock_invest_backend.market.history.dto.BackfillResponse;
import com.example.stock_invest_backend.market.history.dto.CompletenessResult;
import com.example.stock_invest_backend.market.history.dto.IngestResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Service
public class HistoryBackfillService {

    private static final Logger log = LoggerFactory.getLogger(HistoryBackfillService.class);
    private static final DateTimeFormatter YYYYMMDD = DateTimeFormatter.ofPattern("yyyyMMdd");

    private final HistoryDataCompletenessService completenessService;
    private final PythonIngestInvoker invoker;

    public HistoryBackfillService(HistoryDataCompletenessService completenessService,
                                  PythonIngestInvoker invoker) {
        this.completenessService = completenessService;
        this.invoker = invoker;
    }

    public BackfillResponse backfill(String symbol, LocalDate startDate, LocalDate endDate, String adjustType) {
        String requestId = "backfill-" + LocalDate.now().format(YYYYMMDD)
                + "-" + UUID.randomUUID().toString().substring(0, 6);
        long t0 = System.currentTimeMillis();
        log.info("[{}] BACKFILL_START symbol={} range={}~{} adjust={}",
                requestId, symbol, startDate, endDate, adjustType);

        BackfillResponse resp = new BackfillResponse();
        resp.setRequestId(requestId);
        resp.setSymbol(symbol);

        CompletenessResult before = completenessService.check(symbol, startDate, endDate, adjustType);
        resp.setCompletenessBefore(before);

        List<IngestResult> ingestResults = new ArrayList<>();
        if (before.isComplete()) {
            resp.setStatus("OK");
            resp.setCompletenessAfter(before);
            resp.setIngestResults(ingestResults);
            resp.setElapsedMs(System.currentTimeMillis() - t0);
            log.info("[{}] BACKFILL_SKIP already-complete", requestId);
            return resp;
        }

        List<CompletenessResult.MissingRange> ranges = before.getMissingRanges();
        if (ranges == null || ranges.isEmpty()) {
            IngestResult r = invoker.ingestSingle(symbol, startDate, endDate, adjustType, requestId);
            ingestResults.add(r);
        } else {
            for (CompletenessResult.MissingRange range : ranges) {
                IngestResult r = invoker.ingestSingle(symbol, range.getStart(), range.getEnd(), adjustType, requestId);
                ingestResults.add(r);
            }
        }

        CompletenessResult after = completenessService.check(symbol, startDate, endDate, adjustType);
        resp.setCompletenessAfter(after);
        resp.setIngestResults(ingestResults);

        boolean allOk = ingestResults.stream().allMatch(r -> "OK".equals(r.getStatus()));
        boolean noneOk = ingestResults.stream().noneMatch(r -> "OK".equals(r.getStatus()));
        String status;
        if (after.isComplete() && allOk) status = "OK";
        else if (noneOk) status = "FAIL";
        else status = "PARTIAL";
        resp.setStatus(status);
        resp.setElapsedMs(System.currentTimeMillis() - t0);

        log.info("[{}] BACKFILL_END status={} ingestCount={} completeAfter={} elapsedMs={}",
                requestId, status, ingestResults.size(), after.isComplete(), resp.getElapsedMs());
        return resp;
    }
}
