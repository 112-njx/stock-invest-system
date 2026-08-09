<script setup lang="ts">
defineOptions({ name: 'ListRow' })

withDefaults(defineProps<{ clickable?: boolean; active?: boolean }>(), {
  clickable: false,
  active: false,
})
</script>

<template>
  <div class="list-row" :class="{ 'is-clickable': clickable, 'is-active': active }">
    <slot />
  </div>
</template>

<style scoped>
.list-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  font-size: 13px;
  border-bottom: 1px solid var(--border);
}
.list-row:last-child {
  border-bottom: none;
}
.list-row.is-clickable {
  cursor: pointer;
}
.list-row.is-clickable:hover {
  background: var(--bg-hover);
}
.list-row.is-active {
  background: var(--bg-active);
}
</style>
