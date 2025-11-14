<!-- src/components/AcquisitionCard.vue -->
<template>
  <q-card flat bordered class="q-pa-sm q-ma-md">
    <q-card-section class="text-subtitle2 q-py-xs q-px-sm">File acquisition</q-card-section>
    <q-separator />

    <div class="q-pa-sm">
      <div class="row q-col-gutter-sm">
        <div class="col-12">
          <q-input
            v-model="form.folder"
            label="Folder"
            stack-label
            dense outlined filled
          />
        </div>

        <div class="col-12">
          <q-input
            v-model="form.filename"
            label="Filename"
            stack-label
            dense outlined filled
          />
        </div>

        <div class="col-6 col-sm-6">
          <q-input
            v-model.number="form.durationSec"
            label="Duration"
            stack-label
            dense outlined filled
            type="number" inputmode="decimal" suffix="s" :debounce="150"
          />
        </div>

        <div class="col-6 flex items-center q-gutter-sm">
          <q-btn
            color="primary"
            :disable="progress.loading"
            :loading="progress.loading"
            :percentage="progress.percentage"
            @click="startAcquisition"
            style="width: 180px"
          >
            Start acquisition
            <!-- <template #loading>
              <q-spinner-gears class="on-left" />
              Acquiring…
            </template> -->
          </q-btn>

          <q-linear-progress
            v-if="progress.loading || progress.percentage > 0"
            :value="progress.percentage / 100"
            track-color="grey-3"
            class="col grow"
            rounded
          />

          <!-- <div class="text-caption text-grey-7">
            {{ progress.status }}
          </div> -->
        </div>
      </div>
    </div>
  </q-card>
</template>

<script setup lang="ts">
import { reactive } from 'vue'

type FormState = {
  folder: string | null   // directory selection returns files; fine as placeholder
  filename: string
  durationSec: number
}
type ProgressState = {
  loading: boolean
  percentage: number   // 0..100
  status: string
}

const form = reactive<FormState>({
  folder: null,
  filename: 'capture',
  durationSec: 10,
})

const progress = reactive<ProgressState>({
  loading: false,
  percentage: 0,
  status: 'Idle',
})

// Placeholder simulation of a long task with progress
function startAcquisition() {
  if (progress.loading) return
  progress.loading = true
  progress.percentage = 0
  progress.status = 'Preparing…'

  let step = 0
  const timer = setInterval(() => {
    step += 1
    progress.percentage = Math.min(100, step * 5)
    progress.status = progress.percentage < 100 ? 'Acquiring…' : 'Finalizing…'

    if (progress.percentage >= 100) {
      clearInterval(timer)
      setTimeout(() => {
        progress.loading = false
        progress.status = 'Done'
        // keep bar at 100% briefly; reset if you prefer:
        // progress.percentage = 0; progress.status = 'Idle'
      }, 400)
    }
  }, 200)
}
</script>
