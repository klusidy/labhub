<template>
  <q-layout view="lHh LpR lff">
    <q-header elevated>
      <q-toolbar>
        <q-toolbar-title>～ SLM ～</q-toolbar-title>
        <div class="row q-gutter-x-md items-center">
          <span v-if="slm.device" class="text-caption text-grey-3">
            max_phase: {{ slm.device.state.max_phase }} &nbsp;
            offset: {{ slm.device.state.phase_offset }} &nbsp;
            monitor: {{ slm.device.state.monitor_name ?? 'none' }}
          </span>
          <q-badge v-if="!slm.connected" color="negative" label="disconnected" />
        </div>
      </q-toolbar>
    </q-header>

    <!-- Left: Trap controls -->
    <q-drawer v-model="leftOpen" :width="300" show-if-above side="left" bordered class="bg-grey-1">
      <q-scroll-area class="fit">
        <TrapCard />
      </q-scroll-area>
    </q-drawer>

    <!-- Right: Mask controls -->
    <q-drawer v-model="rightOpen" :width="300" show-if-above side="right" bordered class="bg-grey-1">
      <q-scroll-area class="fit">
        <MaskCard />
      </q-scroll-area>
    </q-drawer>

    <q-page-container>
      <q-page class="column q-pa-sm" style="height: 100%">

        <!-- Top row: 3 compact image previews (fixed height) -->
        <div class="row q-col-gutter-sm q-mb-sm" style="height: 300px; flex-shrink: 0">
          <div class="col" style="min-width: 0; min-height: 0">
            <ImageStream device-path="slm/trap" source="trap_img" label="Trap pattern" :rate="5" style="height: 100%" />
          </div>
          <div class="col" style="min-width: 0; min-height: 0">
            <ImageStream device-path="slm/trap" source="overlay_img" label="Overlay pattern" :rate="5" style="height: 100%" />
          </div>
          <div class="col" style="min-width: 0; min-height: 0">
            <ImageStream device-path="slm/mask" source="mask_img" label="Mask" :rate="5" style="height: 100%" />
          </div>
        </div>

        <!-- Large current pattern, fills remaining height -->
        <div class="col" style="min-height: 0; display: flex; flex-direction: column">
          <ImageStream
            device-path="slm"
            source="current_img"
            label="Current pattern (displayed)"
            :rate="5"
            :full-size="true"
            style="flex: 1; min-height: 0"
          />
        </div>

      </q-page>
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
  import { ref, onMounted } from 'vue'
  import { useSlmStore } from 'stores/slm'
  import TrapCard from 'components/TrapCard.vue'
  import MaskCard from 'components/MaskCard.vue'
  import ImageStream from 'components/ImageStream.vue'

  const slm = useSlmStore()
  const leftOpen = ref(true)
  const rightOpen = ref(true)

  onMounted(() => {
    slm.init().catch((err) => console.error('SLM init failed:', err))
  })
</script>
