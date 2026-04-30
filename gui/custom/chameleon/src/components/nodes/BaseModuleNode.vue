<template>
  <div
    class="module-node"
    :class="{ selected, [`node-type-${accentColor}`]: true }"
    :style="{ '--accent': accentHex }"
  >
    <!-- Title bar -->
    <div class="node-header row items-center no-wrap q-px-sm q-py-xs">
      <q-icon :name="icon" size="14px" class="q-mr-xs" :style="{ color: accentHex }" />
      <span class="node-title text-caption text-weight-medium text-white ellipsis">
        {{ data.label }}
      </span>
    </div>

    <!-- Port rows -->
    <div class="node-body q-px-sm q-py-xs">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  data: { label: string; [key: string]: unknown }
  selected?: boolean
  icon?: string
  accentHex?: string
  accentColor?: string
}>()
</script>

<style scoped>
.module-node {
  min-width: 160px;
  background: #2b2b2b;
  border-radius: 6px;
  border: 1px solid #444;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
  transition: border-color 0.15s;
  cursor: pointer;
  font-family: 'Roboto', sans-serif;
}

.module-node.selected {
  border-color: var(--accent);
  box-shadow:
    0 0 0 1px var(--accent),
    0 2px 12px rgba(0, 0, 0, 0.5);
}

.node-header {
  background: rgba(255, 255, 255, 0.05);
  border-bottom: 1px solid #3a3a3a;
  border-radius: 5px 5px 0 0;
  height: 28px;
}

.node-title {
  max-width: 120px;
  line-height: 1;
  font-size: 11px;
}

.node-body {
  padding: 6px 8px;
}
</style>
