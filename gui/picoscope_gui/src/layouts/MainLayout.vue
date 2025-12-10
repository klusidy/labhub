<template>
  <q-layout view="lHh Lpr lFf">
    <q-header elevated>
      <q-toolbar>
        <!-- <q-btn flat dense round icon="menu" aria-label="Menu" @click="toggleLeftDrawer" /> -->

        <q-toolbar-title> ～ Picoscope ～ </q-toolbar-title>

        <div>
          <q-btn
            dense
            outlined
            filled
            spread
            class="full-width q-px-md"
            label="Restart"
            color="blue-8"
            icon="restart_alt"
            size="md"
            :disable="reloading"
            :loading="reloading"
            @click="onRestartClick"
          />
        </div>
      </q-toolbar>
    </q-header>

    <q-drawer v-model="leftDrawerOpen" show-if-above bordered :width="450" class="bg-grey-2">
      <q-list>
        <!-- <q-item-label header> Essential Links </q-item-label> -->
        <ChannelsCard />
        <PropertiesCard />
        <TriggerCard />
        <FileAcquisitionCard />
      </q-list>
    </q-drawer>

    <q-page-container>
      <q-page class="q-pa-0 plot-container">
        <PlotTabs
          v-for="plotTab in plotTabs"
          :key="plotTab.id"
          :plot-area="plotTab.plotArea"
          :removable="plotTabs.length > 1"
          :style="{ height: plotTabHeight, border: '0px solid navy' }"
          @remove="removePlotTab(plotTab.id)"
        />

        <!-- Floating action button to add PlotTab -->
        <q-btn
          fab
          icon="add"
          color="secondary"
          class="add-plot-btn"
          @click="addPlotTab"
        />
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
  import { ref, computed, onMounted, nextTick, watch } from 'vue'
  import ChannelsCard from 'components/ChannelsCard.vue'
  import PropertiesCard from 'components/PropertiesCard.vue'
  import FileAcquisitionCard from 'components/FileAcquisitionCard.vue'
  import TriggerCard from 'components/TriggerCard.vue'
  import PlotTabs from 'components/PlotTabs.vue'
  import { usePicoscopeStore } from 'stores/picoscope'
  import { restartPicoscope } from 'src/api/picoscope'

  const ps = usePicoscopeStore()

  const reloading = ref(false)
  const leftDrawerOpen = ref(false)

  // PlotTab state management
  interface PlotTab {
    id: number
    plotArea: string
  }

  let nextId = 0

  const plotTabs = ref<PlotTab[]>([
    { id: nextId++, plotArea: 'plot-0' },
    { id: nextId++, plotArea: 'plot-1' },
  ])

  // Dynamic height calculation: (100vh - 52px) / number of PlotTabs
  const plotTabHeight = computed(() => {
    const count = plotTabs.value.length
    return `calc((100vh - 52px) / ${count})`
  })

  // Watch for changes in plot tabs count to ensure DOM updates
  watch(() => plotTabs.value.length, async () => {
    await nextTick()
  })

  function addPlotTab() {
    const newId = nextId++
    plotTabs.value.push({
      id: newId,
      plotArea: `plot-${newId}`,
    })
  }

  async function removePlotTab(id: number) {
    // Ensure at least one PlotTab remains
    if (plotTabs.value.length <= 1) return

    const index = plotTabs.value.findIndex((tab) => tab.id === id)
    if (index !== -1) {
      plotTabs.value.splice(index, 1)
      // Force DOM update and recompute heights
      await nextTick()
    }
  }

  function toggleLeftDrawer() {
    leftDrawerOpen.value = !leftDrawerOpen.value
  }

  async function onRestartClick() {
    if (reloading.value) return

    reloading.value = true
    try {
      await restartPicoscope() // wait for server
    } catch (e) {
      console.error('reload failed:', e)
    } finally {
      reloading.value = false
    }
  }

  onMounted(() => {
    ps.init().catch((err) => console.error('picoscope init failed', err))
  })
</script>

<style scoped>
  .plot-container {
    position: relative;
  }

  .add-plot-btn {
    position: fixed;
    bottom: 16px;
    right: 16px;
    z-index: 1000;
  }
</style>
