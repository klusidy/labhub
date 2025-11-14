<!-- src/components/TriggerCard.vue -->
<template>
  <q-card flat bordered class="q-pa-sm q-ma-md">
    <q-card-section class="text-subtitle2 q-py-xs q-px-sm">
      Trigger settings
    </q-card-section>
    <q-separator />

    <div class="q-pa-sm">
      <!-- Row 1: enable, channel, threshold, edge -->
      <div class="row q-col-gutter-sm q-pb-sm items-center">
        

        <div class="col-4 col-sm-4">
          <q-select
            v-model="trigger.channel"
            :options="channelOptions"
            label="Channel"
            stack-label
            dense outlined filled
            emit-value map-options
          />
        </div>

        

        <div class="col-3 col-sm-3">
          <q-select
            v-model="trigger.edge"
            :options="edgeOptions"
            label="Edge"
            stack-label
            dense outlined filled
            emit-value map-options
          />
        </div>
        <div class="col-5 col-sm-5">
          <q-input
            v-model.number="trigger.thresholdMv"
            label="Threshold"
            stack-label
            dense outlined filled
            type="number"
            inputmode="decimal"
            suffix="mV"
            :debounce="150"
          />
        </div>
      </div>

      <!-- Row 2: delay, auto trigger -->
     
      <div class="row q-col-gutter-sm q-pt-xs">
        <div class="col-2 col-sm-2">
          <q-toggle
            v-model="trigger.enabled"
            color="primary"
            dense
            checked-icon="check"
            unchecked-icon="clear"
            size="xl"
          />
        </div>

        <div class="col-6 col-sm-5">
          <q-input
            v-model.number="trigger.delaySamples"
            label="Delay"
            suffix="#"
            stack-label
            dense outlined filled
            type="number"
            inputmode="decimal"
            :debounce="150"
          />
        </div>

        <div class="col-6 col-sm-5">
          <q-input
            v-model.number="trigger.autoTriggerSamples"
            label="Auto trigger"
            suffix="#"
            stack-label
            dense outlined filled
            type="number"
            inputmode="decimal"
            :debounce="150"
          />
        </div>
      </div>
    </div>
  </q-card>
</template>

<script setup lang="ts">
import { reactive } from 'vue'

type Edge = 'rising' | 'falling'

interface TriggerState {
  enabled: boolean
  channel: string
  thresholdMv: number
  edge: Edge
  delaySamples: number
  autoTriggerSamples: number
}

const trigger = reactive<TriggerState>({
  enabled: false,
  channel: 'A',
  thresholdMv: 500,
  edge: 'falling',
  delaySamples: 0,
  autoTriggerSamples: 0,
})

const channelOptions = ['A', 'B', 'C', 'D']

const edgeOptions = [
  { label: '↗',  value: 'rising'  as Edge },
  { label: '↘', value: 'falling' as Edge },
]
</script>
