<!-- src/components/AcquisitionCard.vue -->
<template>
  <q-card flat bordered class="q-pa-sm q-ma-md">
    <q-card-section class="text-subtitle2 q-py-xs q-px-sm row items-center">
      <div>File acquisition</div>

      <q-space />

      <q-btn
        color="primary"
        :disable="in_progress"
        :loading="in_progress"
        @click="startAcquisition"
        style="width: 180px"
        dense
      >
        <!--//:percentage="in_progress" to indicate progress-->
        Start acquisition
      </q-btn>
    </q-card-section>

    <q-separator />

    <div class="q-pa-sm">
      <div class="row q-col-gutter-sm">
        <div class="col-12">
          <q-input
            v-model="form.folder"
            label="Folder"
            stack-label
            dense
            outlined
            filled
            :disable="in_progress"
          />
        </div>

        <div class="col-7 col-sm-7">
          <q-input
            v-model="form.filename"
            :disable="in_progress"
            label="Filename"
            stack-label
            dense
            outlined
            filled
          />
        </div>

        <div class="col-5 col-sm-5">
          <q-input
            v-model.number="form.durationSec"
            :disable="in_progress"
            label="Duration"
            stack-label
            dense
            outlined
            filled
            type="number"
            inputmode="decimal"
            suffix="s"
            :debounce="150"
          />
        </div>
      </div>
    </div>

    <q-separator class="q-mt-sm q-mb-sm" />

    <pre
      class="cmd-result"
      style="
        background: #fafafa;
        border: 1px solid #eee;
        border-radius: 6px;
        padding: 8px;
        margin-top: 8px;
        max-height: 240px;
        overflow: auto;
      "
      >{{ resultText }}</pre
    >
  </q-card>
</template>

<script setup lang="ts">
  import { reactive, ref } from 'vue'
  import { usePicoscopeStore } from 'stores/picoscope'

  const ps = usePicoscopeStore()

  type FormState = {
    folder: string
    filename: string
    durationSec: number
  }

  const form = reactive<FormState>({
    folder: 'C:/Users/jankl/Downloads',
    filename: 'capture',
    durationSec: 1,
  })

  const in_progress = ref<boolean>(false)
  const resultText = ref<string>('{}') // TODO figure out a better way to show results

  async function startAcquisition() {
    if (in_progress.value) return

    in_progress.value = true
    resultText.value = ''

    const args = {
      folder: form.folder,
      filename: form.filename,
      acquisition_duration_s: form.durationSec,
    }
    const r = await ps.acquireToFile(args)
    resultText.value = JSON.stringify(r, null, 2)
    in_progress.value = false
  }
</script>
