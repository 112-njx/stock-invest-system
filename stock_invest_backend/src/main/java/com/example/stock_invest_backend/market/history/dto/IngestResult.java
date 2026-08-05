package com.example.stock_invest_backend.market.history.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public class IngestResult {

    private String requestId;
    private String symbol;
    private String status;
    private String errorCode;
    private String message;
    private Integer rows;
    private Integer affected;
    private Integer batches;
    private String startDate;
    private String endDate;
    private String adjustType;
    private Long elapsedMs;

    public String getRequestId() { return requestId; }
    public void setRequestId(String requestId) { this.requestId = requestId; }

    public String getSymbol() { return symbol; }
    public void setSymbol(String symbol) { this.symbol = symbol; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public String getErrorCode() { return errorCode; }
    public void setErrorCode(String errorCode) { this.errorCode = errorCode; }

    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }

    public Integer getRows() { return rows; }
    public void setRows(Integer rows) { this.rows = rows; }

    public Integer getAffected() { return affected; }
    public void setAffected(Integer affected) { this.affected = affected; }

    public Integer getBatches() { return batches; }
    public void setBatches(Integer batches) { this.batches = batches; }

    public String getStartDate() { return startDate; }
    public void setStartDate(String startDate) { this.startDate = startDate; }

    public String getEndDate() { return endDate; }
    public void setEndDate(String endDate) { this.endDate = endDate; }

    public String getAdjustType() { return adjustType; }
    public void setAdjustType(String adjustType) { this.adjustType = adjustType; }

    public Long getElapsedMs() { return elapsedMs; }
    public void setElapsedMs(Long elapsedMs) { this.elapsedMs = elapsedMs; }
}
