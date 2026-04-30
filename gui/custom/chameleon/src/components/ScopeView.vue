<template>
  <q-page class="scope-page column no-wrap bg-dark">
    <!-- Toolbar -->
    <div class="scope-toolbar row items-center no-wrap q-px-md q-py-xs bg-grey-9">
      <q-btn-group flat>
        <q-btn
          flat
          dense
          :color="streaming ? 'negative' : 'positive'"
          :icon="streaming ? 'stop' : 'play_arrow'"
          :label="streaming ? 'Stop' : 'Stream'"
          size="sm"
          @click="toggleStream"
        />
        <q-btn
          flat
          dense
          color="blue-grey-4"
          icon="photo_camera"
          label="Once"
          size="sm"
          :loading="fetching"
          @click="fetchOnce"
        />
      </q-btn-group>

      <q-separator dark vertical class="q-mx-sm" />

      <div class="row items-center no-wrap q-gutter-x-sm">
        <span class="text-caption text-grey-5">Rate</span>
        <q-input
          v-model.number="streamRate"
          type="number"
          dense
          borderless
          dark
          class="rate-input"
          input-class="text-white text-center"
          :min="1"
          :max="1000"
        />
        <span class="text-caption text-grey-5">Hz</span>
      </div>

      <q-space />

      <div class="row items-center no-wrap q-gutter-x-sm">
        <q-btn-toggle
          v-model="xScale"
          flat
          dense
          toggle-color="primary"
          :options="[{ label: 'LIN', value: 'linear' }, { label: 'LOG', value: 'log' }]"
          size="xs"
        />
        <q-btn-toggle
          v-model="yScale"
          flat
          dense
          toggle-color="primary"
          :options="[{ label: 'LIN', value: 'linear' }, { label: 'LOG', value: 'log' }]"
          size="xs"
        />
      </div>
    </div>

    <!-- Plot area -->
    <div ref="plotContainer" class="col plot-container" />

    <!-- Status bar -->
    <div class="scope-statusbar row items-center q-px-md q-py-xs bg-grey-10">
      <span class="text-caption text-grey-6">
        {{ frameCount }} frames · {{ cs.connected ? 'live' : 'offline' }}
      </span>
      <q-space />
      <span v-if="lastFrameTime" class="text-caption text-grey-7">
        {{ lastFrameTime }}
      </span>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { useChameleonStore } from 'stores/chameleon'
import * as api from 'src/api/chameleon'

const cs = useChameleonStore()

const plotContainer = ref<HTMLElement | null>(null)
const streaming = ref(false)
const fetching = ref(false)
const streamRate = ref(10)
const xScale = ref<'linear' | 'log'>('linear')
const yScale = ref<'linear' | 'log'>('linear')
const frameCount = ref(0)
const lastFrameTime = ref('')

let streamWs: WebSocket | null = null
let plotInitialized = false

// Placeholder trace data
const traces: Plotly.Data[] = [
  {
    x: [] as number[],
    y: [] as number[],
    mode: 'lines',
    name: 'ch0',
    line: { color: '#42a5f5', width: 1.5 },
    type: 'scattergl',
  },
  {
    x: [] as number[],
    y: [] as number[],
    mode: 'lines',
    name: 'ch1',
    line: { color: '#ef5350', width: 1.5 },
    type: 'scattergl',
  },
]

const layout: Partial<Plotly.Layout> = {
  paper_bgcolor: '#121212',
  plot_bgcolor: '#181818',
  font: { color: '#ccc', family: 'Roboto, sans-serif', size: 11 },
  xaxis: {
    color: '#888',
    gridcolor: '#2a2a2a',
    zerolinecolor: '#444',
    title: { text: 'Sample', font: { size: 11 } },
    type: 'linear',
  },
  yaxis: {
    color: '#888',
    gridcolor: '#2a2a2a',
    zerolinecolor: '#444',
    title: { text: 'ADC counts', font: { size: 11 } },
    type: 'linear',
  },
  margin: { l: 52, r: 16, t: 16, b: 44 },
  legend: { bgcolor: 'rgba(0,0,0,0)', font: { size: 10 } },
  uirevision: 'scope',
}

const plotConfig: Partial<Plotly.Config> = {
  responsive: true,
  displayModeBar: true,
  modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
  displaylogo: false,
}

onMounted(() => {
  if (!plotContainer.value) return
  void Plotly.newPlot(plotContainer.value, traces, layout, plotConfig)
  plotInitialized = true
})

onUnmounted(() => {
  streamWs?.close()
  if (plotContainer.value && plotInitialized) {
    Plotly.purge(plotContainer.value)
  }
})

watch(xScale, (v) => {
  if (!plotContainer.value) return
  void Plotly.relayout(plotContainer.value, { 'xaxis.type': v })
})

watch(yScale, (v) => {
  if (!plotContainer.value) return
  void Plotly.relayout(plotContainer.value, { 'yaxis.type': v })
})

function updatePlot(data: unknown) {
  if (!plotContainer.value || !plotInitialized) return

  // Expected format: { ch0: number[], ch1: number[] } or { y: number[][], x?: number[] }
  if (!data || typeof data !== 'object') return
  const d = data as Record<string, unknown>

  const channels = ['ch0', 'ch1']
  const updateTraces: Partial<Plotly.Data>[] = []
  const indices: number[] = []

  channels.forEach((ch, i) => {
    if (Array.isArray(d[ch])) {
      const y = d[ch] as number[]
      const x = (d.x as number[] | undefined) ?? Array.from({ length: y.length }, (_, k) => k)
      updateTraces.push({ x: [x], y: [y] })
      indices.push(i)
    }
  })

  if (updateTraces.length) {
    void Plotly.restyle(plotContainer.value, updateTraces[0] as Plotly.Data, indices)
  }

  frameCount.value++
  lastFrameTime.value = new Date().toLocaleTimeString()
}

async function fetchOnce() {
  fetching.value = true
  try {
    const frame = await api.fetchFrame('scope')
    updatePlot(frame)
  } catch (e) {
    console.error('fetchOnce error:', e)
  } finally {
    fetching.value = false
  }
}

function toggleStream() {
  if (streaming.value) {
    streamWs?.close()
    streamWs = null
    streaming.value = false
  } else {
    streaming.value = true
    streamWs = api.openDataStream('scope', streamRate.value, updatePlot)
    streamWs.onclose = () => {
      streaming.value = false
    }
  }
}
</script>

<style scoped>
.scope-page {
  min-height: 100vh;
}

.scope-toolbar {
  height: 40px;
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
}

.rate-input {
  width: 52px;
}

.plot-container {
  min-height: 0;
}

.scope-statusbar {
  height: 28px;
  flex-shrink: 0;
  border-top: 1px solid rgba(255, 255, 255, 0.07);
}
</style>
