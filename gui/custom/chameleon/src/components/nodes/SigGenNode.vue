<template>
  <BaseModuleNode
    :data="data"
    :selected="selected"
    icon="waves"
    accent-hex="#ffa726"
    accent-color="orange"
  >
    <!-- Input handles (left) -->
    <div
      v-for="(label, i) in inputLabels"
      :key="`in-${i}`"
      class="port-row row items-center"
    >
      <Handle
        :id="`in-${i}`"
        type="target"
        :position="Position.Left"
        :style="handleStyle(i, inputLabels.length, 'left')"
        class="handle-in"
      />
      <span class="port-label text-grey-5 q-ml-sm">{{ label }}</span>
    </div>

    <!-- Output handles (right) -->
    <div
      v-for="(label, i) in outputLabels"
      :key="`out-${i}`"
      class="port-row row items-center justify-end"
    >
      <span class="port-label text-grey-5 q-mr-sm">{{ label }}</span>
      <Handle
        :id="`out-${data.busOutputSlots[i]}`"
        type="source"
        :position="Position.Right"
        :style="handleStyle(inputLabels.length + i, inputLabels.length + outputLabels.length, 'right')"
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

const inputLabels = computed(() => props.data.inputLabels ?? Array.from({ length: props.data.inputCount }, (_, i) => `in${i}`))
const outputLabels = computed(() => props.data.outputLabels ?? props.data.busOutputSlots.map((s) => `slot ${s}`))

function handleStyle(i: number, _total: number, side: 'left' | 'right') {
  const rowHeight = 22
  const topOffset = 42 + i * rowHeight + rowHeight / 2
  return {
    top: `${topOffset}px`,
    [side]: '-6px',
    background: '#ffa726',
  }
}
</script>

<style scoped>
.port-row {
  height: 22px;
  position: relative;
  padding: 0 14px;
}

.port-label {
  font-size: 10px;
  line-height: 1;
}
</style>
