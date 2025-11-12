<template>
  <q-card flat bordered>
    <q-card-section class="text-subtitle2">Channels</q-card-section>
    <q-separator />

    <div class="q-pa-md">
      <!-- header row -->
      <div class="row items-center text-grey-7 q-pb-sm q-mb-sm"
           style="border-bottom: 1px solid rgba(0,0,0,.06);">
        <div class="col-3 col-sm-2 text-caption">Channel</div>
        <div class="col-3 col-sm-2 text-caption">Enabled</div>
        <div class="col-3 col-sm-3 text-caption">Coupling</div>
        <div class="col-3 col-sm-5 text-caption">Range</div>
      </div>

      <!-- rows -->
      <div v-for="ch in channels" :key="ch.id" class="row items-center q-col-gutter-sm q-py-sm">
        <div class="col-3 col-sm-2">
          <div class="text-body2 text-weight-medium">{{ ch.id }}</div>
        </div>

        <div class="col-3 col-sm-2">
          <q-toggle
            v-model="ch.enabled"
            :color="channelColor(ch.id)"
            dense
            keep-color
            checked-icon="check"
            unchecked-icon="clear"
          />
        </div>

        <div class="col-3 col-sm-3">
          <q-select
            v-model="ch.coupling"
            :options="couplingOptions"
            dense outlined
            emit-value map-options
            aria-label="Coupling"
          />
        </div>

        <div class="col-3 col-sm-5">
          <q-select
            v-model="ch.range"
            :options="rangeOptions"
            dense outlined
            emit-value map-options
            use-input
            aria-label="Range"
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
