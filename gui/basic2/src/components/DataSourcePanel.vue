<template>
  <q-card flat bordered class="data-source-panel">
    <q-card-section class="q-pa-none">
      <div v-if="dataSources.length === 0" class="text-grey q-pa-sm">No data sources available</div>

      <q-expansion-item
        v-for="(ds, idx) in dataSources"
        :key="ds.name"
        switch-toggle-side
        :default-opened="idx === 0"
        header-class="data-source-header bg-light-blue-10 text-white"
      >
        <template #header>
          <div class="row items-center full-width no-wrap q-gutter-sm">
            <q-icon name="timeline" color="white" size="sm" />
            <div class="col">
              <span class="text-weight-medium text-body2">{{ ds.name }}</span>
              <q-tooltip v-if="ds.doc" anchor="top middle" self="bottom middle">
                {{ ds.doc }}
              </q-tooltip>
            </div>

            <q-btn
              unelevated
              no-caps
              color="white"
              text-color="light-blue-10"
              label="Once"
              padding="4px 12px"
              :loading="loadingSource === ds.name"
              @click.stop="onOnce(ds.name)"
            />
            <q-btn
              unelevated
              no-caps
              :color="runningSource === ds.name ? 'negative' : 'white'"
              :text-color="runningSource === ds.name ? 'white' : 'light-blue-10'"
              :label="runningSource === ds.name ? 'Stop' : 'Start'"
              padding="4px 12px"
              @click.stop="onToggle(ds.name)"
            />

            <q-input
              v-model.number="rateHz[ds.name]"
              min="0.2"
              step="0.2"
              outlined
              stack-label
              label="Rate"
              dark
              dense
              suffix="Hz"
              style="width: 120px"
              @click.stop
            ></q-input>

            <q-select
              v-model="xScale[ds.name]"
              :options="scaleOptions"
              dense
              label="X scale"
              stack-label
              outlined
              dark
              style="width: 120px"
              @click.stop
            >
            </q-select>

            <q-select
              v-model="yScale[ds.name]"
              :options="scaleOptions"
              outlined
              dense
              label="Y scale"
              stack-label
              dark
              style="width: 120px"
              @click.stop
            >
            </q-select>
          </div>
        </template>

        <q-card flat class="plot-content">
          <q-card-section class="q-pa-xs">
            <div
              :ref="(el) => (plotRefs[ds.name] = el as HTMLElement)"
              class="plot-container"
            ></div>
            <div v-if="errors[ds.name]" class="text-negative text-caption q-mt-xs">
              {{ errors[ds.name] }}
            </div>
          </q-card-section>
        </q-card>
      </q-expansion-item>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { ref, computed, reactive, watch, onUnmounted } from 'vue';
import { useDevicesStore } from 'stores/devices';
import { getPlotSpec, getFrame, openDataStream } from 'src/api/devices';
import type { PlotSpec } from 'src/api/devices';
import Plotly from 'plotly.js-dist-min';

const props = defineProps<{
  deviceId: string;
  filterSource?: string; // If provided, only show this source
}>();

const store = useDevicesStore();
const spec = computed(() => store.getSpecForPath(props.deviceId));

const dataSources = computed(() => {
  const all = spec.value?.data_sources || [];
  if (props.filterSource) {
    return all.filter((ds) => ds.name === props.filterSource);
  }
  return all;
});

const plotRefs = reactive<Record<string, HTMLElement | null>>({});
const rateHz = reactive<Record<string, number>>({});
const xScale = reactive<Record<string, string>>({});
const yScale = reactive<Record<string, string>>({});
const errors = reactive<Record<string, string | null>>({});
const loadingSource = ref<string | null>(null);
const runningSource = ref<string | null>(null);
const websockets = reactive<Record<string, WebSocket | null>>({});
const plotSpecs = reactive<Record<string, PlotSpec>>({});
const plotData = reactive<Record<string, { x: number[]; series: Record<string, number[]> }>>({});

const scaleOptions = ['linear', 'log'];

// Initialize defaults
watch(
  dataSources,
  (sources) => {
    for (const ds of sources) {
      if (rateHz[ds.name] === undefined) rateHz[ds.name] = 10;
      if (xScale[ds.name] === undefined) xScale[ds.name] = 'linear';
      if (yScale[ds.name] === undefined) yScale[ds.name] = 'linear';
    }
  },
  { immediate: true },
);

// Watch scale changes and update plots
watch(
  () => Object.entries(xScale),
  () => updateAllPlots(),
  { deep: true },
);
watch(
  () => Object.entries(yScale),
  () => updateAllPlots(),
  { deep: true },
);

async function loadSpec(sourceName: string) {
  try {
    const ps = await getPlotSpec(props.deviceId, sourceName);
    plotSpecs[sourceName] = ps;
    return ps;
  } catch (e) {
    errors[sourceName] = e instanceof Error ? e.message : String(e);
    return null;
  }
}

async function onOnce(sourceName: string) {
  loadingSource.value = sourceName;
  errors[sourceName] = null;

  try {
    await loadSpec(sourceName);
    const frame = await getFrame(props.deviceId, sourceName);
    applyFrame(sourceName, frame);
    updatePlot(sourceName);
  } catch (e) {
    errors[sourceName] = e instanceof Error ? e.message : String(e);
  } finally {
    loadingSource.value = null;
  }
}

function onToggle(sourceName: string) {
  if (runningSource.value === sourceName) {
    stopStream(sourceName);
  } else {
    void startStream(sourceName);
  }
}

async function startStream(sourceName: string) {
  errors[sourceName] = null;

  // Stop any existing stream
  stopStream(sourceName);

  try {
    await loadSpec(sourceName);
    runningSource.value = sourceName;

    const ws = openDataStream(props.deviceId, sourceName, rateHz[sourceName]);
    websockets[sourceName] = ws;

    ws.onmessage = (event) => {
      try {
        const frame = JSON.parse(event.data);
        if (frame?.type === 'plot_metadata' && frame?.plot) {
          plotSpecs[sourceName] = frame.plot;
        } else {
          applyFrame(sourceName, frame);
          updatePlot(sourceName);
        }
      } catch {
        // Ignore parse errors
      }
    };

    ws.onerror = () => {
      errors[sourceName] = 'Stream error';
    };

    ws.onclose = () => {
      if (runningSource.value === sourceName) {
        runningSource.value = null;
      }
      websockets[sourceName] = null;
    };
  } catch (e) {
    errors[sourceName] = e instanceof Error ? e.message : String(e);
  }
}

function stopStream(sourceName: string) {
  const ws = websockets[sourceName];
  if (ws) {
    ws.close();
    websockets[sourceName] = null;
  }
  if (runningSource.value === sourceName) {
    runningSource.value = null;
  }
}

function applyFrame(sourceName: string, frame: unknown) {
  const ps = plotSpecs[sourceName];
  const xValues = (ps?.['x-values'] as number[]) || [];

  // Initialize data structure
  if (!plotData[sourceName]) {
    plotData[sourceName] = { x: [], series: {} };
  }

  const data = plotData[sourceName];

  // Extract x values
  const fr = frame as Record<string, unknown>;
  if (Array.isArray(fr?.['x-values'])) {
    data.x = fr['x-values'] as number[];
  } else if (Array.isArray(fr?.x)) {
    data.x = fr.x as number[];
  } else if (xValues.length) {
    data.x = xValues;
  }

  // Extract series data
  // Format 1: { series: [{name, data}, ...] }
  if (Array.isArray(fr?.series)) {
    for (const s of fr.series as { name: string; data: number[] }[]) {
      if (Array.isArray(s?.data)) {
        data.series[s.name || 'data'] = s.data;
      }
    }
    return;
  }

  // Format 2: { data: [...] }
  if (Array.isArray(fr?.data)) {
    data.series['data'] = fr.data as number[];
    return;
  }

  // Format 3: { A: [...], B: [...] } (object of arrays)
  for (const [key, val] of Object.entries(fr || {})) {
    if (
      key === 'meta' ||
      key === 'x' ||
      key === 'x-values' ||
      key === 'name' ||
      key === 'series' ||
      key === 'type'
    )
      continue;
    if (Array.isArray(val) && val.every((n) => typeof n === 'number')) {
      data.series[key] = val;
    }
  }

  // Build x if not present
  if (!data.x.length) {
    const firstSeries = Object.values(data.series)[0];
    if (firstSeries) {
      data.x = firstSeries.map((_, i) => i);
    }
  }
}

const COLORS = [
  '#2d6cdf',
  '#d9534f',
  '#5cb85c',
  '#f0ad4e',
  '#5bc0de',
  '#6f42c1',
  '#20c997',
  '#fd7e14',
];

function updatePlot(sourceName: string) {
  const el = plotRefs[sourceName];
  if (!el) return;

  const data = plotData[sourceName];
  if (!data) return;

  const ps = plotSpecs[sourceName];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const traces: any[] = [];

  let i = 0;
  for (const [name, yData] of Object.entries(data.series)) {
    traces.push({
      x: data.x,
      y: yData,
      name,
      type: 'scatter',
      mode: 'lines',
      line: { color: COLORS[i % COLORS.length], width: 2 },
    });
    i++;
  }

  const layout = {
    title: { text: ps?.title || sourceName, font: { size: 14 } },
    xaxis: {
      title: { text: ps?.['x-label'] || '', font: { size: 11 } },
      type: xScale[sourceName] === 'log' ? 'log' : 'linear',
    },
    yaxis: {
      title: { text: ps?.['y-label'] || '', font: { size: 11 } },
      type: yScale[sourceName] === 'log' ? 'log' : 'linear',
    },
    margin: { t: 30, b: 35, l: 45, r: 10 },
    showlegend: traces.length > 1,
    legend: { orientation: 'h', y: -0.15, font: { size: 10 } },
  };

  void Plotly.react(el, traces, layout, { responsive: true, displayModeBar: false });
}

function updateAllPlots() {
  for (const sourceName of Object.keys(plotData)) {
    updatePlot(sourceName);
  }
}

// Cleanup on unmount
onUnmounted(() => {
  for (const sourceName of Object.keys(websockets)) {
    stopStream(sourceName);
  }
});
</script>

<style scoped>
.data-source-panel {
  margin-bottom: 12px;
}

.data-source-header {
  min-height: 48px;
  padding: 8px 12px;
}

:deep(.q-expansion-item__toggle-icon) {
  color: white;
}

.plot-content {
  background: white;
}

.plot-container {
  width: 100%;
  height: 280px;
}

.rate-input :deep(.q-field__control) {
  height: 32px;
}

.scale-select :deep(.q-field__control) {
  height: 32px;
}

.rate-input :deep(input) {
  padding: 0 4px;
}
</style>
