<template>
  <div ref="rootEl" class="plot-root row no-wrap flex q-ma-zero q-pa-zero">
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
          :disable="running"
          @click="fetchAndUpdateOnce"
        />

        <q-btn
          dense
          outlined
          filled
          spread
          rounded
          size="md"
          :label="running ? 'Stop' : 'Start'"
          :color="running ? 'red' : 'green'"
          class="full-width"
          :icon="running ? 'stop_circle' : 'play_circle'"
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
          :disable="running"
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
  import type { Data, PlotlyHTMLElement, Layout } from 'plotly.js'
  import { usePicoscopeStore } from 'stores/picoscope'
  import { usePlotSettingsStore } from 'stores/plotSettings'
  import type { PlotSettings } from 'src/types/plotSettings'
  import { getFrame, openDataStream } from 'src/api/picoscope' // adjust path
  import type { Frame, ChannelId, PlotSpec } from 'src/api/picoscope'
  import { last } from 'lodash-es'

  const ps = usePicoscopeStore()
  const plotSettingsStore = usePlotSettingsStore()

  const spec = ref<PlotSpec | null>(null)

  let ws: WebSocket | null = null

  const lastFrame = ref<Frame | null>(null)

  const props = defineProps<{
    name: string
    title?: string
    plotArea: string
  }>()

  const rootEl = ref<HTMLElement | null>(null)
  const el = ref<PlotlyHTMLElement | null>(null)
  let plotted = false
  let resizeObserver: ResizeObserver | null = null

  const running = ref(false)
  const rateHz = ref(10)

  // Load initial scale settings from store
  const settings = plotSettingsStore.getSettings(props.plotArea, props.name)
  const xScaleLocal = ref<'linear' | 'log'>(settings.xScale)
  const yScaleLocal = ref<'linear' | 'log'>(settings.yScale)

  const CHANNEL_COLORS: Record<ChannelId, string> = {
    A: '#2196f3', // blue
    B: '#f44336', // red
    C: '#4caf50', // green
    D: '#ffc107', // amber/orange
  }

  watch(
    () => ps.plotSpecs?.[props.name],
    (newSpec) => {
      if (newSpec) {
        spec.value = newSpec
        // If we already plotted a frame, redraw using new spec
        // if (plotted && lastFrame.value) { // avoid double redraw?
        //   void updatePlotFromFrame(lastFrame.value)
        // }
      }
    },
    { immediate: true } // so first spec loads instantly
  )

  // frame is whatever I get from frame API/WS
  // data is what plotly needs
  function buildDataFromFrame(frame: Frame): Data[] {
    const xVals = spec.value?.['x-values']
    const chanKeys: ChannelId[] = (['A', 'B', 'C', 'D'] as ChannelId[])
      .filter((ch) => ps.channels()?.[ch].enable === 1) // only enabled channels
      .filter((ch) => Array.isArray(frame[ch])) // only those present in frame

    return chanKeys.map((ch) => {
      const multiplier = spec.value?.channel_settings?.[ch]?.multiplier || 1 // apply multiplier if present
      const y = (frame[ch] as number[]).map((v) => v * multiplier)
      const x = xVals || y.map((_, i) => i) // default to simple index on X

      return {
        x,
        y,
        mode: 'lines',
        type: 'scattergl',
        name: ch,
        line: { color: CHANNEL_COLORS[ch] },
      }
    })
  }

  function buildLayout(): Record<string, unknown> {
    const settings = plotSettingsStore.getSettings(props.plotArea, props.name)

    return {
      title: props.title ?? '',
      margin: { t: 40, l: 60, r: 10, b: 40 },
      xaxis: {
        title: {
          text: spec.value?.['x-label'] ?? '',
          standoff: 10,
        },
        type: xScaleLocal.value,
        autorange: !settings.zoom.active || !settings.zoom.xRange,
      },
      yaxis: {
        title: {
          text: spec.value?.['y-label'] ?? '',
          standoff: 10,
        },
        type: yScaleLocal.value,
        autorange: !settings.zoom.active || !settings.zoom.yRange,
      },
      showlegend: true,
      uirevision: 'keep-zoom',
    }
  }

  /**
   * Capture current zoom state from Plotly and persist to store
   */
  function captureZoomState() {
    if (!el.value || !plotted) return

    const layout = el.value.layout
    const xaxis = layout.xaxis
    const yaxis = layout.yaxis

    const zoomState: PlotSettings['zoom'] = {
      active: !xaxis.autorange || !yaxis.autorange,
      xType: xaxis.type as 'linear' | 'log',
      yType: yaxis.type as 'linear' | 'log',
    }

    // Only add ranges if they exist
    if (!xaxis.autorange && xaxis.range) {
      zoomState.xRange = xaxis.range as [number, number]
    }
    if (!yaxis.autorange && yaxis.range) {
      zoomState.yRange = yaxis.range as [number, number]
    }

    plotSettingsStore.updateZoom(props.plotArea, props.name, zoomState)
  }

  /**
   * Restore saved zoom state to Plotly after initial plot creation
   */
  function restoreZoomState() {
    if (!el.value || !plotted) return

    const settings = plotSettingsStore.getSettings(props.plotArea, props.name)

    if (!settings.zoom.active) return // User wants autoscale

    const update: Partial<Layout> = {}

    // Only restore X range if scale types match (handle scale switch edge case)
    if (settings.zoom.xRange && settings.zoom.xType === xScaleLocal.value) {
      const [r0, r1] = settings.zoom.xRange

      // Validate log scale ranges (must be positive)
      if (xScaleLocal.value === 'log' && (r0 <= 0 || r1 <= 0)) {
        update['xaxis.autorange'] = true
      } else {
        update['xaxis.range'] = settings.zoom.xRange
        update['xaxis.autorange'] = false
      }
    }

    // Same for Y axis
    if (settings.zoom.yRange && settings.zoom.yType === yScaleLocal.value) {
      const [r0, r1] = settings.zoom.yRange

      if (yScaleLocal.value === 'log' && (r0 <= 0 || r1 <= 0)) {
        update['yaxis.autorange'] = true
      } else {
        update['yaxis.range'] = settings.zoom.yRange
        update['yaxis.autorange'] = false
      }
    }

    if (Object.keys(update).length > 0) {
      void Plotly.relayout(el.value, update)
    }
  }

  async function updatePlotFromFrame(frame: Frame) {
    if (!el.value) return

    const data = buildDataFromFrame(frame)
    const layout = buildLayout()

    if (!plotted) {
      await Plotly.newPlot(el.value, data, layout, {
        responsive: true,
        displaylogo: false,
        scrollZoom: true,
      })
      plotted = true

      // Attach relayout event listener to capture zoom changes
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(el.value as any).on('plotly_relayout', (eventData: Record<string, unknown>) => {
        // Ignore programmatic scale changes (from our own watchers)
        if (eventData['xaxis.type'] || eventData['yaxis.type']) {
          return
        }

        // Detect zoom/pan/autoscale events
        const hasXZoom = 'xaxis.range[0]' in eventData && 'xaxis.range[1]' in eventData
        const hasYZoom = 'yaxis.range[0]' in eventData && 'yaxis.range[1]' in eventData
        const isAutoscale = eventData['xaxis.autorange'] || eventData['yaxis.autorange']

        if (hasXZoom || hasYZoom || isAutoscale) {
          // Use setTimeout to ensure layout is fully updated
          setTimeout(captureZoomState, 0)
        }
      })

      // Restore saved zoom state after initial plot
      setTimeout(restoreZoomState, 100)
    } else {
      void Plotly.react(el.value, data, layout)
    }
  }

  async function fetchAndUpdateOnce() {
    // getPlot specs as well!!!
    const spec: PlotSpec = await ps.fetchPlotSpec(props.name)
    const frame: Frame = await getFrame(props.name)
    lastFrame.value = frame
    await updatePlotFromFrame(frame)
  }

  function onStartStop() {
    if (running.value) {
      //running.value = false
      stopStream()
    } else {
      // running.value = true
      startStream()
    }
  }

  watch(
    () => [props.name, props.title] as const, //, xScaleLocal.value, yScaleLocal.value
    () => {
      if (!plotted) return
      if (!lastFrame.value) return
      void updatePlotFromFrame(lastFrame.value)
    }
  )

  watch(xScaleLocal, (newScale, oldScale) => {
    // Persist scale change to store
    plotSettingsStore.updateScale(props.plotArea, props.name, 'x', newScale)

    if (!plotted || !el.value) return
    const gd = el.value
    const full = gd.layout.xaxis
    const oldRange = full?.range as [number, number] | undefined

    const update: Partial<Layout> = {}

    if (!oldRange || oldRange[0] === oldRange[1]) {
      // no useful range → just flip type and autorange
      update['xaxis.type'] = newScale
      update['xaxis.autorange'] = true
      void Plotly.relayout(gd, update)
      return
    }

    const [r0, r1] = oldRange

    if (oldScale === 'linear' && newScale === 'log') {
      // r0, r1 are in data units
      if (r0 > 0 && r1 > 0) {
        update['xaxis.type'] = 'log'
        update['xaxis.range'] = [Math.log10(r0), Math.log10(r1)]
      } else {
        update['xaxis.type'] = 'log'
        update['xaxis.autorange'] = true
      }
    } else if (oldScale === 'log' && newScale === 'linear') {
      // r0, r1 are log10(data)
      update['xaxis.type'] = 'linear'
      update['xaxis.range'] = [Math.pow(10, r0), Math.pow(10, r1)]
    } else {
      // same scale? or unexpected combo
      update['xaxis.type'] = newScale
      update['xaxis.autorange'] = true
    }

    void Plotly.relayout(gd, update)
  })

  watch(yScaleLocal, (newScale, oldScale) => {
    // Persist scale change to store
    plotSettingsStore.updateScale(props.plotArea, props.name, 'y', newScale)

    if (!plotted || !el.value) return
    const gd = el.value
    const full = gd.layout?.yaxis
    const oldRange = full?.range as [number, number] | undefined

    const update: Partial<Layout> = {}

    if (!oldRange || oldRange[0] === oldRange[1]) {
      update['yaxis.type'] = newScale
      update['yaxis.autorange'] = true
      void Plotly.relayout(gd, update)
      return
    }

    const [r0, r1] = oldRange

    if (oldScale === 'linear' && newScale === 'log') {
      if (r0 > 0 && r1 > 0) {
        update['yaxis.type'] = 'log'
        update['yaxis.range'] = [Math.log10(r0), Math.log10(r1)]
      } else {
        update['yaxis.type'] = 'log'
        update['yaxis.autorange'] = true
      }
    } else if (oldScale === 'log' && newScale === 'linear') {
      update['yaxis.type'] = 'linear'
      update['yaxis.range'] = [Math.pow(10, r0), Math.pow(10, r1)]
    } else {
      update['yaxis.type'] = newScale
      update['yaxis.autorange'] = true
    }

    void Plotly.relayout(gd, update)
  })

  function stopStream() {
    if (ws) {
      try {
        ws.close()
      } catch (e) {
        console.error('error closing WS', e)
      }
      ws = null
    }
    running.value = false
  }

  function startStream() {
    // close any existing stream first
    stopStream()

    try {
      ws = openDataStream(props.name, rateHz.value, 'json')
      running.value = true

      ws.onmessage = (ev: MessageEvent) => {
        try {
          const raw =
            typeof ev.data === 'string' ? ev.data : new TextDecoder().decode(ev.data as ArrayBuffer)

          const frame = JSON.parse(raw) as Frame
          lastFrame.value = frame
          void updatePlotFromFrame(frame)
        } catch (e) {
          console.error('failed to parse stream frame', e)
        }
      }

      ws.onerror = (ev) => {
        console.error('stream error', ev)
      }

      ws.onclose = () => {
        // freeze on last frame
        ws = null
        running.value = false
      }
    } catch (e) {
      console.error('openDataStream failed', e)
      running.value = false
      ws = null
    }
  }

  onMounted(async () => {
    if (lastFrame.value) await updatePlotFromFrame(lastFrame.value)

    // Set up ResizeObserver to handle container size changes
    if (rootEl.value) {
      resizeObserver = new ResizeObserver(() => {
        if (el.value && plotted) {
          // Trigger Plotly resize when container changes size
          Plotly.Plots.resize(el.value)
        }
      })

      // Observe the root element which is resized by parent
      resizeObserver.observe(rootEl.value)
    }
  })

  onBeforeUnmount(() => {
    // Clean up ResizeObserver
    if (resizeObserver) {
      resizeObserver.disconnect()
      resizeObserver = null
    }

    if (el.value) Plotly.purge(el.value)
    stopStream()
  })
</script>

<style scoped>
  .plot-root {
    display: flex;
    height: 100%;
    overflow: hidden;
  }

  .plot-controls {
    width: 170px;
    min-width: 160px;
    max-width: 220px;
    height: 100%;
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
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
