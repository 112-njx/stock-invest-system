import { ref } from 'vue';
import { useRouter } from 'vue-router';

const STOCK_LIST = [
  { symbol: 'sh600519', name: '贵州茅台' },
  { symbol: 'sz000001', name: '平安银行' },
  { symbol: 'sz000002', name: '万科A' },
  { symbol: 'sh000001', name: '上证指数' },
  { symbol: 'sz399001', name: '深证成指' },
  { symbol: 'sz399006', name: '创业板指' },
];

export function useStockSearch() {
  const router = useRouter();
  const keyword = ref('');
  const suggestions = ref<{ symbol: string; name: string }[]>([]);

  function onSearch(value: string) {
    keyword.value = value.toUpperCase();
    if (!keyword.value) {
      suggestions.value = [];
      return;
    }
    suggestions.value = STOCK_LIST.filter(
      (s) => s.symbol.includes(keyword.value) || s.name.includes(value),
    );
  }

  function selectStock(symbol: string) {
    keyword.value = '';
    suggestions.value = [];
    router.replace(`/stock/${symbol}`);
  }

  function onEnter() {
    if (keyword.value) {
      const match = STOCK_LIST.find((s) => s.symbol === keyword.value);
      if (match) {
        selectStock(match.symbol);
      } else if (/^(SH|SZ|BJ)\d{6}$/i.test(keyword.value)) {
        selectStock(keyword.value.toLowerCase());
      } else {
        selectStock(keyword.value);
      }
    }
  }

  return { keyword, suggestions, onSearch, selectStock, onEnter };
}
