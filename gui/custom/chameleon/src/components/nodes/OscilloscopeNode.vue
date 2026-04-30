<template>
  <BaseModuleNode
    :data="data"
    :selected="selected"
    icon="show_chart"
    accent-hex="#66bb6a"
    accent-color="green"
  >
    <div
      v-for="(label, i) in inputLabels"
      :key="i"
      class="port-row row items-center"
    >
      <Handle
        :id="`in-${i}`"
        type="target"
        :position="Position.Left"
        :style="handleStyle(i, inputLabels.length)"
        class="handle-in"
      />
      <span class="port-label text-grey-5 q-ml-sm">{{ label }}</span>
      <q-space />
      <span class="mux-badge text-grey-6">{{ muxLabel(i) }}</span>
    </div>
  </BaseModuleNode>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position, useVueFlow } from '@vue-flow/core'
import BaseModuleNode from './BaseModuleNode.vue'
import type { ModuleNodeData } from 'components/CanvasPanel.vue'

const props = defineProps<{
  id: string
  data: ModuleNodeData
  selected: boolean
}>()

const inputLabels = computed(() => props.data.inputLabels ?? Array.from({ length: props.data.inputCount }, (_, i) => `in${i}`))

const { edges } = useVueFlow()

function muxLabel(inputIdx: number): string {
  const handleId = `in-${inputIdx}`
  const edge = edges.value.find((e) => e.target === props.id && e.targetHandle === handleId)
  if (!edge) return '—'
  const slotMatch = edge.sourceHandle?.match(/^out-(\d+)$/)
  return slotMatch ? `slot ${slotMatch[1]}` : '?'
}

function handleStyle(i: number, _total: number) {
  const rowHeight = 22
  const topOffset = 42 + i * rowHeight + rowHeight / 2
  return { top: `${topOffset}px`, left: '-6px', background: '#66bb6a' }
}
</script>

<style scoped>
.port-row {
  height: 22px;
  position: relative;
  padding-left: 14px;
  padding-right: 4px;
}

.port-label {
  font-size: 10px;
  line-height: 1;
}

.mux-badge {
  font-size: 9px;
  font-family: monospace;
}
</style>
