<template>
  <div class="bordered q-pa-0 q-ma-0" style="border:0px solid lime">
   
    <q-tabs
        v-model="tab"
        dense
        align="left"
        class="bg-green text-white shadow-2 text-subtitle2 text-weight-regular"
        
      >
        <q-tab name="time_stream" label="Time stream" /> 
        <q-tab name="psd"  label="PSD" />
        <q-tab name="psd_avg"  label="PSD ( averaged)" />
    </q-tabs>


        <q-tab-panels
          v-model="tab"
          animated
          swipeable
          vertical
          transition-prev="jump-up"
          transition-next="jump-up"
          class="q-pa-0 q-ma-0"
          style="border:0px solid gold; width:100%; height:calc(100% - 35px);"
  
          
        >
          <q-tab-panel name="time_stream" class="q-pa-none q-ma-none fit"  >
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

          <q-tab-panel name="psd_avg" class="q-pa-none q-ma-none fit"  >
                <PlotView
                kind="time"
                x-scale="linear"
                y-scale="linear"
                :title="`Time series`"
                x-label="t"
                y-label="V"
                />
        </q-tab-panel>
        </q-tab-panels> 
  

  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
//import PlotView from './PlotView.vue';
import PlotView from 'components/PlotView.vue'


// const { title, subtitle } = defineProps<{
//   title?: string
//   subtitle?: string
// }>()

const tab = ref<'time_stream' | 'psd' | 'psd_avg'>('time_stream')
// const xScale = ref<'linear' | 'log'>('linear')
// const yScale = ref<'linear' | 'log'>('linear')



// const scaleOptions = [
//   { label: 'linear', value: 'linear' as const },
//   { label: 'log', value: 'log' as const },
// ]

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
  height: 100%;        /* PlotView fills the panel */
}
</style>
