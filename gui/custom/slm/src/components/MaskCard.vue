<template>
  <q-card flat bordered class="q-ma-sm">
    <q-card-section class="text-subtitle2 q-py-xs q-px-sm">Mask</q-card-section>
    <q-separator />

    <q-card-section class="q-pa-sm q-gutter-y-sm">

      <!-- Vertical stripe -->
      <div class="text-caption text-grey-6 q-mb-xs">Vertical stripe</div>
      <q-toggle
        v-model="verticalShow"
        label="Show vertical stripe"
        @update:model-value="patch({ vertical_show: verticalShow })"
      />

      <div>
        <div class="row items-center q-gutter-x-sm">
          <div class="col text-caption" :class="verticalShow ? 'text-grey-7' : 'text-grey-4'">
            Start column (idx)
          </div>
          <div class="col-auto text-caption" :class="!verticalShow ? 'text-grey-4' : ''">
            {{ verticalIdx }}
          </div>
        </div>
        <div style="position: relative">
          <q-slider
            v-model="verticalIdx"
            :min="0"
            :max="2000"
            :step="1"
            snap
            :disable="!verticalShow"
            @change="patch({ vertical_idx: verticalIdx })"
          />
          <div v-if="!verticalShow" style="position: absolute; inset: 0; cursor: not-allowed">
            <q-tooltip>Enable vertical stripe first</q-tooltip>
          </div>
        </div>
      </div>

      <div style="position: relative">
        <q-input
          v-model.number="verticalSize"
          label="Width (px)"
          type="number"
          dense
          outlined
          filled
          stack-label
          :disable="!verticalShow"
          :debounce="600"
          @update:model-value="patch({ vertical_size: verticalSize })"
        />
        <div v-if="!verticalShow" style="position: absolute; inset: 0; cursor: not-allowed">
          <q-tooltip>Enable vertical stripe first</q-tooltip>
        </div>
      </div>

      <q-separator />

      <!-- Horizontal stripe -->
      <div class="text-caption text-grey-6 q-mb-xs">Horizontal stripe</div>
      <q-toggle
        v-model="horizontalShow"
        label="Show horizontal stripe"
        @update:model-value="patch({ horizontal_show: horizontalShow })"
      />

      <div>
        <div class="row items-center q-gutter-x-sm">
          <div class="col text-caption" :class="horizontalShow ? 'text-grey-7' : 'text-grey-4'">
            Start row (idx)
          </div>
          <div class="col-auto text-caption" :class="!horizontalShow ? 'text-grey-4' : ''">
            {{ horizontalIdx }}
          </div>
        </div>
        <div style="position: relative">
          <q-slider
            v-model="horizontalIdx"
            :min="0"
            :max="2000"
            :step="1"
            snap
            :disable="!horizontalShow"
            @change="patch({ horizontal_idx: horizontalIdx })"
          />
          <div v-if="!horizontalShow" style="position: absolute; inset: 0; cursor: not-allowed">
            <q-tooltip>Enable horizontal stripe first</q-tooltip>
          </div>
        </div>
      </div>

      <div style="position: relative">
        <q-input
          v-model.number="horizontalSize"
          label="Height (px)"
          type="number"
          dense
          outlined
          filled
          stack-label
          :disable="!horizontalShow"
          :debounce="600"
          @update:model-value="patch({ horizontal_size: horizontalSize })"
        />
        <div v-if="!horizontalShow" style="position: absolute; inset: 0; cursor: not-allowed">
          <q-tooltip>Enable horizontal stripe first</q-tooltip>
        </div>
      </div>

    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
  import { ref, watch } from 'vue'
  import { useSlmStore } from 'stores/slm'
  import type { MaskState } from 'src/api/slm'

  const slm = useSlmStore()

  const verticalShow = ref(false)
  const verticalIdx = ref(0)
  const verticalSize = ref(100)
  const horizontalShow = ref(false)
  const horizontalIdx = ref(0)
  const horizontalSize = ref(100)

  watch(
    () => slm.device?.state.mask,
    (mask) => {
      if (!mask) return
      verticalShow.value = mask.vertical_show
      verticalIdx.value = mask.vertical_idx
      verticalSize.value = mask.vertical_size
      horizontalShow.value = mask.horizontal_show
      horizontalIdx.value = mask.horizontal_idx
      horizontalSize.value = mask.horizontal_size
    },
    { immediate: true }
  )

  async function patch(props: Partial<MaskState>) {
    await slm.patchMask(props)
  }
</script>
