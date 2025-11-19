<template>
  <div class="plot-root row no-wrap flex q-ma-zero q-pa-zero">
    <!-- Left control column -->
    <div class="plot-controls column q-pa-sm q-gutter-sm q-mx-zero q-my-zero">
      <div class="col items-center q-gutter-y-md q-pt-md">
        <!-- <div class="text-subtitle2 text-center q-mt-lg">{{ title || kind }}</div>
        <q-separator /> -->
        <q-btn
          dense
          outlined
          filled
          spread
          rounded
          class="full-width"
          label="Once"
          color="green"
          icon="refresh"
          @click="onOnce"
        />

        <q-btn
          dense
          outlined
          filled
          spread
          rounded
          size="md"
          :label="running ? 'Stop' : 'Start'"
          color="green"
          class="full-width"
          icon="play_circle"
          @click="onStartStop"
        />

        <q-input
          v-model.number="rateHz"
          label="Rate"
          suffix="Hz"
          dense
          outlined
          filled
          type="number"
          inputmode="decimal"
          :min="0.1"
          :step="0.1"
        />

        <div class="row q-gutter-xs">
          <div class="text-body2">X scale</div>
          <q-btn-toggle
            v-model="xScaleLocal"
            dense
            size="sm"
            class="col"
            spread
            toggle-color="primary"
            :options="[
              { label: 'LIN', value: 'linear' },
              { label: 'LOG', value: 'log' },
            ]"
          />
        </div>

        <div class="row q-gutter-xs">
          <div class="text-body2">Y scale</div>
          <q-btn-toggle
            v-model="yScaleLocal"
            dense
            size="sm"
            class="col"
            spread
            toggle-color="primary"
            :options="[
              { label: 'LIN', value: 'linear' },
              { label: 'LOG', value: 'log' },
            ]"
          />
        </div>
      </div>
    </div>

    <!-- Plot area -->
    <div class="plot-area col">
      <div ref="el" class="plot-div"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
  import Plotly from 'plotly.js-dist-min'
  import type { Data } from 'plotly.js'
  import { usePicoscopeStore } from 'stores/picoscope'
  import { getFrame } from 'src/api/picoscope' // adjust path

  const props = defineProps<{
    kind: string
    title?: string
    xLabel?: string
    yLabel?: string
    xScale: 'linear' | 'log'
    yScale: 'linear' | 'log'
  }>()

  const el = ref<HTMLDivElement | null>(null)
  let plotted = false

  const running = ref(false)
  const rateHz = ref(10)

  const xScaleLocal = ref<'linear' | 'log'>(props.xScale)
  const yScaleLocal = ref<'linear' | 'log'>(props.yScale)

  watch(
    () => props.xScale,
    (v) => (xScaleLocal.value = v)
  )
  watch(
    () => props.yScale,
    (v) => (yScaleLocal.value = v)
  )

  let timer: number | null = null

  // --- placeholder data, just to see something --- //
  function buildDummyData(kind: typeof props.kind): Data[] {
    const n = 500
    const x = Array.from({ length: n }, (_, i) => i * 0.1)
    const y = x.map((t) => {
      if (kind === 'psd') return 1 / Math.sqrt(t + 1) + 0.05 * Math.random()
      if (kind === 'psd_avg') return 1 / (t + 1) + 0.02 * Math.random()
      return 0.01 * Math.sin(t) + 0.005 * (Math.random() - 0.5)
    })
    return [
      {
        x,
        y,
        mode: 'lines',
        type: 'scattergl', // WebGL, good for many points
        name: kind,
      },
    ]
  }

  function buildLayout(): Record<string, unknown> {
    return {
      title: props.title ?? '',
      margin: { t: 40, l: 60, r: 10, b: 40 },
      xaxis: {
        title: props.xLabel ?? '',
        type: xScaleLocal.value,
      },
      yaxis: {
        title: props.yLabel ?? '',
        type: yScaleLocal.value,
      },
      uirevision: 'keep-zoom',
    }
  }

  async function drawInitial() {
    if (!el.value) return
    const data = buildDummyData(props.kind)
    await Plotly.newPlot(el.value, data, buildLayout(), {
      responsive: true,
      displaylogo: false,
      scrollZoom: true,
    })
    plotted = true
  }

  function updatePlot() {
    if (!el.value || !plotted) return
    const data = buildDummyData(props.kind)
    void Plotly.react(el.value, data, buildLayout())
  }

  function onOnce() {
    updatePlot()
  }

  function clearTimer() {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  function startTimer() {
    clearTimer()
    const intervalMs = Math.max(10, Math.round(1000 / Math.max(rateHz.value, 0.1)))
    timer = window.setInterval(() => {
      updatePlot()
    }, intervalMs)
  }

  function onStartStop() {
    if (running.value) {
      running.value = false
      clearTimer()
    } else {
      running.value = true
      startTimer()
    }
  }

  watch(rateHz, () => {
    if (running.value) startTimer()
  })

  watch(
    () =>
      [
        props.kind,
        props.title,
        props.xLabel,
        props.yLabel,
        xScaleLocal.value,
        yScaleLocal.value,
      ] as const,
    () => {
      if (!plotted) return
      updatePlot()
    }
  )

  onMounted(async () => {
    await drawInitial()
  })

  onBeforeUnmount(() => {
    clearTimer()
    if (el.value) Plotly.purge(el.value)
  })
</script>

<style scoped>
  .plot-root {
    display: flex;
    height: 100%;
    overflow: hidden; /* kill scrollbars here */
  }

  .plot-controls {
    width: 170px; /* tune to taste */
    min-width: 160px;
    max-width: 220px;
    height: 100%;
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
    /* background-color: lime;  // keep only if debugging */
  }

  .plot-area {
    flex: 1 1 auto;
    height: 100%;
    min-width: 0;
    display: flex;
  }

  .plot-div {
    flex: 1 1 auto;
    width: 100%;
    height: 100%;
  }
</style>
