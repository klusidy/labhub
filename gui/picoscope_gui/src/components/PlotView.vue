<template>
  <div ref="el" style="width: 100%; height: 100%;"></div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
//import Plotly, { Data, Layout } from 'plotly.js-dist-min'
// import Plotly from 'plotly.js-dist-min'
// import type { Data, Layout, LayoutAxis } from 'plotly.js'
import Plotly from 'plotly.js-dist-min'
import type { Data } from 'plotly.js'

const props = defineProps<{
  kind: 'time' | 'psd' | 'psd_avg'
  title?: string
  xLabel?: string
  yLabel?: string
  xScale: 'linear' | 'log'
  yScale: 'linear' | 'log'
}>()

const el = ref<HTMLDivElement | null>(null)
let plotted = false

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
      type: props.xScale,
    },
    yaxis: {
      title: props.yLabel ?? '',
      type: props.yScale,
    },
    uirevision: 'keep-zoom',
  }
}

onMounted(async () => {
  if (!el.value) return
  const data = buildDummyData(props.kind)
  await Plotly.newPlot(el.value, data, buildLayout(), {
    responsive: true,
    displaylogo: false,
    scrollZoom: true,
  })
  plotted = true
})

watch(
  () => [props.kind, props.xScale, props.yScale, props.title, props.xLabel, props.yLabel] as const,
  () => {
    if (!el.value) return
    if (!plotted) return

    // update data kind
    const data = buildDummyData(props.kind)
    void Plotly.react(el.value, data, buildLayout())
  }
)

onBeforeUnmount(() => {
  if (el.value) Plotly.purge(el.value)
})
</script>
