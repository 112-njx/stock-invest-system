<template>
  <div class="stock-search-input">
    <el-autocomplete
      v-model="keyword"
      :fetch-suggestions="fetchSuggestions"
      placeholder="输入股票代码或名称"
      size="small"
      class="search-box"
      :popper-append-to-body="false"
      @select="onSelect"
      @keyup.enter="onEnter"
      clearable
    >
      <template #default="{ item }">
        <span>{{ item.value }}</span>
        <span style="color: #888; margin-left: 8px;">{{ item.name }}</span>
      </template>
    </el-autocomplete>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';

interface StockItem {
  value: string;
  name: string;
}

const STOCK_LIST: StockItem[] = [
  { value: 'sh600519', name: '贵州茅台' },
  { value: 'sz000001', name: '平安银行' },
  { value: 'sz000002', name: '万科A' },
  { value: 'sh000001', name: '上证指数' },
  { value: 'sz399001', name: '深证成指' },
  { value: 'sz399006', name: '创业板指' },
];

const router = useRouter();
const keyword = ref('');

function fetchSuggestions(queryString: string, callback: (results: StockItem[]) => void) {
  if (!queryString) {
    callback(STOCK_LIST);
    return;
  }
  const upper = queryString.toUpperCase();
  callback(STOCK_LIST.filter((s) => s.value.includes(upper) || s.name.includes(queryString)));
}

function onSelect(item: StockItem) {
  selectStock(item.value);
}

function selectStock(symbol: string) {
  keyword.value = '';
  router.replace(`/stock/${symbol}`);
}

function onEnter() {
  if (keyword.value) {
    const match = STOCK_LIST.find((s) => s.value === keyword.value || s.name === keyword.value);
    if (match) {
      selectStock(match.value);
    } else if (/^(SH|SZ|BJ)\d{6}$/i.test(keyword.value)) {
      selectStock(keyword.value.toLowerCase());
    } else {
      selectStock(keyword.value);
    }
  }
}
</script>

<style scoped>
.stock-search-input {
  position: absolute;
  top: 8px;
  right: 336px;
  z-index: 150;
  width: 280px;
}
.search-box {
  width: 100%;
}
</style>
