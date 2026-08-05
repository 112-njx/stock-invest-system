<template>
  <div class="app-shell">
    <div class="app-shell-left">
      <slot name="left" />
    </div>
    <div class="app-shell-right">
      <slot name="right" />
    </div>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  width: 100%;
  height: calc(100vh - 28px);
}
.app-shell-left {
  flex: 1;
  min-width: 0;
  position: relative;
}
.app-shell-right {
  width: 320px;
  flex-shrink: 0;
  border-left: 1px solid #333;
  overflow-y: auto;
}
</style>
