package com.example.stock_invest_backend.market.history.dto;

import java.util.List;

public class BackfillResponse {

    private String requestId;
    private String symbol;
    private String status;
    private List<IngestResult> ingestResults;
    private CompletenessResult completenessBefore;
    private CompletenessResult completenessAfter;
    private long elapsedMs;

    public String getRequestId() { return requestId; }
    public void setRequestId(String requestId) { this.requestId = requestId; }

    public String getSymbol() { return symbol; }
    public void setSymbol(String symbol) { this.symbol = symbol; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public List<IngestResult> getIngestResults() { return ingestResults; }
    public void setIngestResults(List<IngestResult> ingestResults) { this.ingestResults = ingestResults; }

    public CompletenessResult getCompletenessBefore() { return completenessBefore; }
    public void setCompletenessBefore(CompletenessResult completenessBefore) { this.completenessBefore = completenessBefore; }

    public CompletenessResult getCompletenessAfter() { return completenessAfter; }
    public void setCompletenessAfter(CompletenessResult completenessAfter) { this.completenessAfter = completenessAfter; }

    public long getElapsedMs() { return elapsedMs; }
    public void setElapsedMs(long elapsedMs) { this.elapsedMs = elapsedMs; }
}
