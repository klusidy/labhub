<template>
  <BaseModuleNode
    :data="data"
    :selected="selected"
    icon="input"
    accent-hex="#42a5f5"
    accent-color="blue"
  >
    <div v-for="(label, i) in outputLabels" :key="i" class="port-row row items-center justify-end">
      <span class="port-label text-grey-5">{{ label }}</span>
      <Handle
        :id="`out-${data.busOutputSlots[i]}`"
        type="source"
        :position="Position.Right"
        :style="handleStyle(i, outputLabels.length)"
        class="handle-out"
      />
    </div>
  </BaseModuleNode>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import BaseModuleNode from './BaseModuleNode.vue'
import type { ModuleNodeData } from 'components/CanvasPanel.vue'

const props = defineProps<{
  id: string
  data: ModuleNodeData
  selected: boolean
}>()

const outputLabels = computed(() => props.data.outputLabels ?? props.data.busOutputSlots.map((s) => `slot ${s}`))

function handleStyle(i: number, total: number) {
  const rowHeight = 22
  const topOffset = 42 + i * rowHeight + rowHeight / 2
  return { top: `${topOffset}px`, right: '-6px', background: '#42a5f5' }
}
</script>

<style scoped>
.port-row {
  height: 22px;
  position: relative;
  padding-right: 14px;
}

.port-label {
  font-size: 10px;
  line-height: 1;
}

.handle-out {
  position: absolute;
  right: -5px;
}
</style>
