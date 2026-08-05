<template>
  <div class="five-level-quotes">
    <div class="level-title">五档盘口</div>
    <div class="level-table">
      <div class="level-sell" v-for="i in 5" :key="'s' + i">
        <span class="label">卖{{ 6 - i }}</span>
        <span class="price sell-color">--</span>
        <span class="vol">--</span>
      </div>
      <div class="level-buy" v-for="i in 5" :key="'b' + i">
        <span class="label">买{{ i }}</span>
        <span class="price buy-color">--</span>
        <span class="vol">--</span>
      </div>
    </div>
    <p class="placeholder-hint">阶段6接入实时盘口数据</p>
  </div>
</template>

<style scoped>
.five-level-quotes { padding: 8px 12px; border-top: 1px solid #333; }
.level-title { font-size: 12px; color: #888; margin-bottom: 4px; }
.level-table { font-size: 11px; }
.level-sell, .level-buy { display: flex; gap: 8px; padding: 1px 0; }
.label { width: 28px; color: #888; }
.price { width: 56px; text-align: right; }
.vol { flex: 1; text-align: right; color: #666; }
.sell-color { color: #00B050; }
.buy-color { color: #EF5350; }
.placeholder-hint { font-size: 10px; color: #444; text-align: center; margin-top: 4px; }
</style>
