<template>
  <q-layout view="lHh Lpr lFf">
    <q-header elevated>
      <q-toolbar>
        <q-btn flat dense round icon="menu" aria-label="Menu" @click="toggleLeftDrawer" />

        <q-toolbar-title> Picoscope </q-toolbar-title>

        <div>Quasar v{{ $q.version }}</div>
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
          style="height: calc(50vh - 26px); border: 0px solid navy"
        />
        <PlotTabs
          title="Plot B"
          subtitle="bottom"
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

  const ps = usePicoscopeStore()

  onMounted(() => {
    ps.init().catch((err) => console.error('picoscope init failed', err))
  })

  const leftDrawerOpen = ref(false)

  function toggleLeftDrawer() {
    leftDrawerOpen.value = !leftDrawerOpen.value
  }
</script>
