package com.example.stock_invest_backend.lof.service;

import com.example.stock_invest_backend.lof.dto.LofPremiumItem;
import com.example.stock_invest_backend.lof.dto.LofPremiumRankRequest;
import com.example.stock_invest_backend.lof.dto.LofPremiumRankResponse;
import com.example.stock_invest_backend.lof.dto.LofPremiumStatus;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

import java.util.Comparator;
import java.util.List;

@Service
public class LofPremiumRankService {

    private final LofPremiumSourceService lofPremiumSourceService;

    public LofPremiumRankService(LofPremiumSourceService lofPremiumSourceService) {
        this.lofPremiumSourceService = lofPremiumSourceService;
    }

    public Mono<LofPremiumRankResponse> rank(LofPremiumRankRequest request) {
        final int safeLimit = Math.max(1, Math.min(nullSafeLimit(request.getLimit()), 200));
        final String order = normalizeOrder(request.getOrder());
        final boolean onlyStatusOk = Boolean.TRUE.equals(request.getOnlyStatusOk());

        return lofPremiumSourceService.fetchPremiums(List.of())
                .map(response -> {
                    List<LofPremiumItem> items = response.getItems();
                    if (onlyStatusOk) {
                        items = items.stream()
                                .filter(item -> item.getStatus() == LofPremiumStatus.OK)
                                .toList();
                    }

                    // tradingOnly is reserved by L3 and intentionally not applied in L2 stage.
                    List<LofPremiumItem> ranked = items.stream()
                            .sorted(buildComparator(order))
                            .limit(safeLimit)
                            .toList();

                    LofPremiumRankResponse rankResponse = new LofPremiumRankResponse();
                    rankResponse.setItems(ranked);
                    rankResponse.setTotal(ranked.size());
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
