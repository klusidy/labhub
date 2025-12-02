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
      <q-page class="q-pa-0">
        <PlotTabs
          title="Plot A"
          subtitle="top"
          plot-area="top"
          style="height: calc(50vh - 26px); border: 0px solid navy"
        />
        <PlotTabs
          title="Plot B"
          subtitle="bottom"
          plot-area="bottom"
          style="height: calc(50vh - 26px); border: 0px solid navy"
        />
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
  import { ref } from 'vue'
  import ChannelsCard from 'components/ChannelsCard.vue'
  import PropertiesCard from 'components/PropertiesCard.vue'
  import FileAcquisitionCard from 'components/FileAcquisitionCard.vue'
  import TriggerCard from 'components/TriggerCard.vue'

  import PlotTabs from 'components/PlotTabs.vue'

  import { onMounted } from 'vue'
  import { usePicoscopeStore } from 'stores/picoscope'
  import { restartPicoscope } from 'src/api/picoscope'

  const ps = usePicoscopeStore()

  const reloading = ref(false)

  onMounted(() => {
    ps.init().catch((err) => console.error('picoscope init failed', err))
  })

  const leftDrawerOpen = ref(false)

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
</script>
