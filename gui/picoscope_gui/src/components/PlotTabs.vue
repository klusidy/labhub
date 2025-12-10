<template>
  <div class="bordered q-pa-0 q-ma-0" style="border: 0px solid lime; height: 100%">
    <div class="tabs-header">
      <q-tabs
        v-model="tab"
        dense
        align="left"
        class="bg-secondary text-white shadow-2 text-subtitle2 text-weight-regular tabs-flex"
      >
        <q-tab v-for="s in sources" :key="s.key" :name="s.key" :label="s.title" />

        <q-btn
          v-if="props.removable"
          flat
          dense
          square
          icon="close"
          color="white"
          class="close-btn bg-secondary"
          @click="emit('remove')"
        />
      </q-tabs>

      <!-- Close button on the right -->
    </div>

    <q-tab-panels
      v-model="tab"
      animated
      vertical
      keep-alive
      transition-prev="jump-up"
      transition-next="jump-up"
      class="q-pa-0 q-ma-0"
      style="width: 100%; height: calc(100% - 35px)"
    >
      <q-tab-panel v-for="s in sources" :key="s.key" :name="s.key" class="q-pa-none q-ma-none fit">
        <PlotView :name="s.key" :plot-area="props.plotArea" :title="s.title" />
      </q-tab-panel>
    </q-tab-panels>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, watch } from 'vue'
  import { usePicoscopeStore } from 'stores/picoscope'
  import PlotView from 'components/PlotView.vue'

  const props = defineProps<{
    plotArea: string
    removable?: boolean
  }>()

  const emit = defineEmits<{
    remove: []
  }>()

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

  .tabs-header {
    display: flex;
    align-items: center;
    background-color: var(--q-secondary);
  }

  .tabs-flex {
    flex: 1;
  }

  .close-btn {
    position: absolute;
    bottom: 2px;
    right: 0px;
    z-index: 1000;
  }
</style>
