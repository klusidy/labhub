<template>
  <q-card flat bordered class="q-pa-sm q-ma-md">
    <q-card-section class="text-subtitle2 q-py-xs q-px-sm">
      Channels
    </q-card-section>
    <q-separator />

    <div class="q-pa-xs">
      <div
        v-for="row in channelList"
        :key="row.id"
        class="row items-center q-col-gutter-sm q-py-xs q-pa-xs"
      >
        <div class="col-1">
          <div class="text-body4 text-weight-medium">{{ row.id }}</div>
        </div>

        <!-- enabled toggle -->
        <div class="col-2">
          <q-toggle
            v-model="local[row.id].enabled"
            :color="channelColor(row.id)"
            dense
            keep-color
            checked-icon="check"
            unchecked-icon="clear"
            size="xl"
            @update:model-value="applyChannelUpdate(row.id)"
          />
        </div>

        <!-- coupling -->
        <div class="col-4">
          <q-select
            v-model="local[row.id].coupling"
            :options="couplingOptions"
            dense
            outlined
            filled
            label="Coupling"
            stack-label
            emit-value
            map-options
            @update:model-value="applyChannelUpdate(row.id)"
          />
        </div>

        <!-- range -->
        <div class="col-5">
          <q-select
            v-model="local[row.id].range"
            :options="rangeOptions"
            dense outlined filled
            label="Range"
            emit-value map-options
            use-input
            @update:model-value="applyChannelUpdate(row.id)"
          />
        </div>
      </div>
    </div>
  </q-card>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { debounce } from 'lodash-es'
import { usePicoscopeStore } from 'stores/picoscope'
import type { HwChannelId, Range } from 'src/api/picoscope'

const ps = usePicoscopeStore()



interface UIChannel {
  id: HwChannelId
  enabled: boolean
  coupling: 'AC' | 'DC'
  range: Range
}

interface LocalChannel {
  enabled: boolean
  coupling: 'AC' | 'DC'
  range: Range
}

const couplingOptions = [
  { label: 'DC', value: 'DC' },
  { label: 'AC', value: 'AC' },
]

const rangeOptions = [
  '10MV','20MV','50MV','100MV','200MV','500MV',
  '1V','2V','5V','10V','20V'
]

const local = reactive<Record<HwChannelId, LocalChannel>>({
  A: { enabled: false, coupling: 'DC', range: '1V' },
  B: { enabled: false, coupling: 'DC', range: '1V' },
  C: { enabled: false, coupling: 'DC', range: '1V' },
  D: { enabled: false, coupling: 'DC', range: '1V' },
})

// array form for template v-for
const channelList = computed(() =>
  (['A','B','C','D'] as HwChannelId[]).map(id => ({ id }))
)

// sync backend → local UI state
watch(
  () => ps.channels(),
  ch => {
    if (!ch) return
    for (const id of ['A','B','C','D'] as HwChannelId[]) {
      if (!ch[id]) continue
      local[id].enabled  = ch[id].enable
      local[id].coupling = ch[id].coupling
      local[id].range    = ch[id].range
    }
  },
  { immediate: true }
)

// debounced update to backend
import { toRaw } from 'vue'
function applyChannelUpdate(id: HwChannelId) {
  void debouncedChannelUpdate(id, { ...toRaw(local[id]) }) // snapshot current UI state
}

const debouncedChannelUpdate = debounce(async (id: HwChannelId, ch: LocalChannel) => {
  const v = local[id]

  await ps.patchChannel(id, {
    enable: v.enabled,
    coupling: v.coupling,
    range: v.range,
  })
}, 200)



function channelColor(id: string): string { // todo - refactor channel color elsewhere
  switch (id) {
    case 'A': return 'blue'
    case 'B': return 'red'
    case 'C': return 'green'
    case 'D': return 'amber'
    default:  return 'primary'
  }
}
</script>
