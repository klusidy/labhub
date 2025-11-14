<!-- src/components/PropertiesCard.vue -->
<template>
  <q-card flat bordered class="q-pa-sm q-ma-md">
    <q-card-section class="text-subtitle2 q-py-xs q-px-sm">Properties</q-card-section>
    <q-separator />

    <div class="q-pa-xs">
    
      <!-- <div v-for="p in rows" :key="p.key" class="row items-center q-col-gutter-sm q-py-xs"> -->
    <div class="row q-col-gutter-sm q-pa-sm">
      <div v-for="p in rows" :key="p.key" class="col-12 col-sm-6">

        <div class="col-6 col-sm-6">
          <q-input
            v-model="p.requested"
            :label="p.label"
            stack-label
            dense outlined filled type="number" :inputmode="'decimal'" :suffix="p.unit || ''" :debounce="300"
            :readonly="p.readonly || false"
            >
            <q-tooltip v-if="p.hint">
             {{p.hint}}
            </q-tooltip>
         </q-input>
        </div>
    </div>
   </div>
   </div>
  </q-card>
</template>

<script setup lang="ts">
import { reactive } from 'vue'

type NumberRow = {
  key: string
  label: string
  unit?: string
  hint?: string
  requested: number
  actual?: number
  readonly?: boolean
}

const rows = reactive<NumberRow[]>([
  { key: 'fs',   label: 'Sampling frequency', unit: 'Hz',     requested: 1_000_000 , readonly: false, hint: 'Current sampling frequency in Hz.'},
  { key: 'ts',   label: 'Sampling time',      unit: 'ns',     requested: 10, readonly: true },
  { key: 'preN', label: 'Pre-trigger',        unit: '#',requested: 1024, readonly: false },
  { key: 'preT', label: 'Pre-trigger',        unit: 's',requested: 0.01, readonly: true },

  { key: 'postN',label: 'Post-trigger',       unit: '#',requested: 4096, readonly: false },
  { key: 'postT',label: 'Post-trigger',       unit: 's',requested: 0.1 , readonly: true},
  { key: 'down', label: 'Downsample window',                    requested: 10, readonly: false },
])
</script>

<style scoped>
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
</style>
