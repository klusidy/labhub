<template>
  <q-card flat bordered class="q-pa-sm q-ma-md">
  <q-card-section class="text-subtitle2 q-py-xs q-px-sm">Channels</q-card-section>
  <q-separator />

    <div class="q-pa-xs">
    
      <!-- rows -->
      <div v-for="ch in channels" :key="ch.id" class="row items-center q-col-gutter-sm q-py-xs  q-pa-xs">
        <div class="col-1 col-sm-1">
          <div class="text-body4 text-weight-medium">{{ ch.id }}</div>
        </div>

        <div class="col-2 col-sm-2">
          <q-toggle
            v-model="ch.enabled"
            :color="channelColor(ch.id)"
            dense
            options-dense
            keep-color
            checked-icon="check"
            unchecked-icon="clear"
            size="xl"
          />
        </div>

        <div class="col-4 col-sm-4">
          <q-select
            v-model="ch.coupling"
            :options="couplingOptions"
            dense 
            options-dense
            outlined
            emit-value map-options
            filled 
            label="Coupling" 
            stack-label />
        </div>

        <div class="col-5 col-sm-5">
          <q-select
            v-model="ch.range"
            :options="rangeOptions"
            dense outlined
            emit-value map-options
            use-input
            filled
            label="Range"
          />
        </div>
      </div>
    </div>
  </q-card>
</template>

<script setup lang="ts">
import { reactive } from 'vue'

const couplingOptions = [
  { label: 'DC', value: 'DC' },
  { label: 'AC', value: 'AC' },
]

// Tweak ranges to your device’s capabilities later
const rangeOptions = ['10MV','20MV', '50MV', '100MV', '200MV', '500MV',
                      '1V', '2V', '5V', '10V', '20V', '50V']


const channels = reactive([
  { id: 'A', enabled: false, coupling: 'DC', range: '1V' },
  { id: 'B', enabled: false, coupling: 'DC', range: '1V' },
  { id: 'C', enabled: false, coupling: 'DC', range: '1V' },
  { id: 'D', enabled: false, coupling: 'DC', range: '1V' },
])

function channelColor(id:string): string {
  // distinct colors per channel (tweak as you like)
  switch (id) {
    case 'A': return 'blue'
    case 'B': return 'red'
    case 'C': return 'green'
    case 'D': return 'amber'
    default:  return 'primary'
  }
}

// Later: expose channels via emits/Pinia when wiring to backend
</script>
