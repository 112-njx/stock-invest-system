package com.example.stock_invest_backend.market.history.dto;

import java.time.LocalDate;
import java.util.List;

public class CompletenessResult {

    private String symbol;
    private String adjustType;
    private LocalDate startDate;
    private LocalDate endDate;
    private int expected;
    private int actual;
    private boolean complete;
    private List<MissingRange> missingRanges;
    private String message;

    public static class MissingRange {
        private LocalDate start;
        private LocalDate end;

        public MissingRange() {}

        public MissingRange(LocalDate start, LocalDate end) {
            this.start = start;
            this.end = end;
        }

        public LocalDate getStart() { return start; }
        public void setStart(LocalDate start) { this.start = start; }

        public LocalDate getEnd() { return end; }
        public void setEnd(LocalDate end) { this.end = end; }
    }

    public String getSymbol() { return symbol; }
    public void setSymbol(String symbol) { this.symbol = symbol; }

    public String getAdjustType() { return adjustType; }
    public void setAdjustType(String adjustType) { this.adjustType = adjustType; }

    public LocalDate getStartDate() { return startDate; }
    public void setStartDate(LocalDate startDate) { this.startDate = startDate; }

    public LocalDate getEndDate() { return endDate; }
    public void setEndDate(LocalDate endDate) { this.endDate = endDate; }

    public int getExpected() { return expected; }
    public void setExpected(int expected) { this.expected = expected; }

    public int getActual() { return actual; }
    public void setActual(int actual) { this.actual = actual; }

    public boolean isComplete() { return complete; }
    public void setComplete(boolean complete) { this.complete = complete; }

    public List<MissingRange> getMissingRanges() { return missingRanges; }
    public void setMissingRanges(List<MissingRange> missingRanges) { this.missingRanges = missingRanges; }

    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }
}
