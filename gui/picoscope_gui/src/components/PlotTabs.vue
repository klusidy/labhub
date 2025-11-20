<template>
  <div class="bordered q-pa-0 q-ma-0" style="border: 0px solid lime">
    <q-tabs
      v-model="tab"
      dense
      align="left"
      class="bg-secondary text-white shadow-2 text-subtitle2 text-weight-regular"
    >
      <!-- <q-tab name="time_stream" label="Time stream" />
      <q-tab name="psd" label="PSD" />
      <q-tab name="psd_avg" label="PSD ( averaged)" /> -->
      <q-tab v-for="s in sources" :key="s.key" :name="s.key" :label="s.title" />
    </q-tabs>

    <q-tab-panels
      v-model="tab"
      animated
      swipeable
      vertical
      keep-alive
      transition-prev="jump-up"
      transition-next="jump-up"
      class="q-pa-0 q-ma-0"
      style="width: 100%; height: calc(100% - 35px)"
    >
      <q-tab-panel v-for="s in sources" :key="s.key" :name="s.key" class="q-pa-none q-ma-none fit">
        <PlotView :name="s.key" x-scale="linear" y-scale="linear" :title="s.title" />
      </q-tab-panel>

      <!-- <q-tab-panel name="time_stream" class="q-pa-none q-ma-none fit">
        <PlotView
          kind="time"
          x-scale="linear"
          y-scale="linear"
          :title="`Time series`"
          x-label="t"
          y-label="V"
        />
      </q-tab-panel>

      <q-tab-panel name="psd" class="q-pa-none q-ma-none fit">
        <PlotView
          kind="time"
          x-scale="linear"
          y-scale="linear"
          :title="`Time series`"
          x-label="t"
          y-label="V"
        />
      </q-tab-panel>

      <q-tab-panel name="psd_avg" class="q-pa-none q-ma-none fit">
        <PlotView
          kind="time"
          x-scale="linear"
          y-scale="linear"
          :title="`Time series`"
          x-label="t"
          y-label="V"
        />
      </q-tab-panel> -->
    </q-tab-panels>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, watch } from 'vue'
  import { usePicoscopeStore } from 'stores/picoscope'
  import PlotView from 'components/PlotView.vue'

  const ps = usePicoscopeStore()

  //const tab = ref<'time_stream' | 'psd' | 'psd_avg'>('time_stream')

  const sources = computed(() => {
    const ds = ps.spec?.data_sources ?? []
    return ds
      .filter((s) => s.has_plot)
      .map((s) => {
        const plot = ps.plotSpecs[s.name]
        return {
          key: s.name,
          // use title from /plot if available, otherwise fallback
          title: plot?.title ?? s.name.replace(/_/g, ' ').toUpperCase(),
          // other values from plot specs are irrelevant here
        }
      })
  })

  const tab = ref<string>('')

  watch(
    sources,
    (list) => {
      if (list && list.length && !tab.value) {
        tab.value = list[0]?.key || ''
      }
    },
    { immediate: true }
  )
</script>

<style scoped>
  .plot-card {
    min-height: 260px;
  }

  .plot-panel {
    padding: 0;
    height: 100%;
  }

  .plot-panel > div {
    height: 100%; /* PlotView fills the panel */
  }
</style>
