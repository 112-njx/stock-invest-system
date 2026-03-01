package com.example.stock_invest_backend.lof.service;

import com.example.stock_invest_backend.lof.dto.LofPremiumItem;
import com.example.stock_invest_backend.lof.dto.LofPremiumRankRequest;
import com.example.stock_invest_backend.lof.dto.LofPremiumRankResponse;
import com.example.stock_invest_backend.lof.dto.LofPremiumStatus;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

import java.util.Comparator;
import java.util.List;

/*
这是lof基金排序规则的实现
主排序：premiumRate(溢价率)
副排序：quoteTime(报价时间)
 */
@Service
public class LofPremiumRankService {

    private final LofPremiumSourceService lofPremiumSourceService;
    private final LofTradingSessionService tradingSessionService;

    public LofPremiumRankService(LofPremiumSourceService lofPremiumSourceService,
                                 LofTradingSessionService tradingSessionService) {
        this.lofPremiumSourceService = lofPremiumSourceService;
        this.tradingSessionService = tradingSessionService;
    }

    public Mono<LofPremiumRankResponse> rank(LofPremiumRankRequest request) {
        final int safeLimit = Math.max(1, Math.min(nullSafeLimit(request.getLimit()), 200));
        final String order = normalizeOrder(request.getOrder());
        final boolean onlyStatusOk = Boolean.TRUE.equals(request.getOnlyStatusOk());
        final boolean tradingOnly = Boolean.TRUE.equals(request.getTradingOnly());
        final boolean tradingOpen = tradingSessionService.isTradingOpenNow();

        return lofPremiumSourceService.fetchPremiums(List.of())
                .map(response -> {
                    LofPremiumRankResponse rankResponse = new LofPremiumRankResponse();
                    rankResponse.setTradingWindow(tradingOpen ? "OPEN" : "CLOSED");
                    List<String> filtersApplied = new java.util.ArrayList<>();

                    if (tradingOnly) {
                        filtersApplied.add("tradingOnly");
                        if (!tradingOpen) {
                            rankResponse.setItems(List.of());
                            rankResponse.setTotal(0);
                            rankResponse.setFiltersApplied(filtersApplied);
                            rankResponse.setMessage("trading window is closed");
                            return rankResponse;
                        }
                    }

                    List<LofPremiumItem> items = response.getItems();
                    if (onlyStatusOk) {
                        filtersApplied.add("onlyStatusOk");
                        items = items.stream()
                                .filter(item -> item.getStatus() == LofPremiumStatus.OK)
                                .toList();
                    }

                    List<LofPremiumItem> ranked = items.stream()
                            .sorted(buildComparator(order))
                            .limit(safeLimit)
                            .toList();

                    rankResponse.setItems(ranked);
                    rankResponse.setTotal(ranked.size());
                    rankResponse.setFiltersApplied(filtersApplied);
                    rankResponse.setMessage("ok");
                    return rankResponse;
                });
    }

    private Comparator<LofPremiumItem> buildComparator(String order) {
        Comparator<LofPremiumItem> quoteTimeDesc =
                Comparator.comparing(LofPremiumItem::getQuoteTime, Comparator.nullsLast(Comparator.reverseOrder()));
        if ("asc".equals(order)) {
            return Comparator.comparing(
                            LofPremiumItem::getPremiumRate,
                            Comparator.nullsLast(Comparator.naturalOrder()))
                    .thenComparing(quoteTimeDesc);
        }
        return Comparator.comparing(
                        LofPremiumItem::getPremiumRate,
                        Comparator.nullsLast(Comparator.reverseOrder()))
                .thenComparing(quoteTimeDesc);
    }

    private String normalizeOrder(String order) {
        if (order == null) {
            return "desc";
        }
        String normalized = order.trim().toLowerCase();
        return "asc".equals(normalized) ? "asc" : "desc";
    }

    private int nullSafeLimit(Integer limit) {
        return limit == null ? 20 : limit;
    }
}
