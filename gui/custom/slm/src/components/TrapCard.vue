<template>
  <q-card flat bordered class="q-ma-sm">
    <q-card-section class="text-subtitle2 q-py-xs q-px-sm">Trap</q-card-section>
    <q-separator />

    <q-card-section class="q-pa-sm q-gutter-y-sm">

      <!-- Beam type -->
      <q-select
        v-model="beamType"
        :options="['gauss', 'bessel']"
        label="Beam type"
        dense
        outlined
        filled
        stack-label
        @update:model-value="patch({ beam_type: beamType })"
      />

      <!-- x -->
      <div>
        <div class="row items-center q-gutter-x-xs">
          <div class="col text-caption text-grey-7">x</div>
          <div class="col-auto text-caption">{{ x.toFixed(4) }}</div>
          <q-btn flat dense round size="xs" icon="adjust" @click="zero('x')" title="Zero x">
            <q-tooltip>Set x = 0</q-tooltip>
          </q-btn>
        </div>
        <q-slider v-model="x" :min="-0.5" :max="0.5" :step="0.001" snap @change="patch({ x })" />
      </div>

      <!-- y -->
      <div>
        <div class="row items-center q-gutter-x-xs">
          <div class="col text-caption text-grey-7">y</div>
          <div class="col-auto text-caption">{{ y.toFixed(4) }}</div>
          <q-btn flat dense round size="xs" icon="adjust" @click="zero('y')" title="Zero y">
            <q-tooltip>Set y = 0</q-tooltip>
          </q-btn>
        </div>
        <q-slider v-model="y" :min="-0.5" :max="0.5" :step="0.001" snap @change="patch({ y })" />
      </div>

      <!-- z -->
      <div>
        <div class="row items-center q-gutter-x-xs">
          <div class="col text-caption text-grey-7">z (axial)</div>
          <div class="col-auto text-caption">{{ z.toExponential(2) }}</div>
          <q-btn flat dense round size="xs" icon="adjust" @click="zero('z')" title="Zero z">
            <q-tooltip>Set z = 0</q-tooltip>
          </q-btn>
        </div>
        <q-slider v-model="z" :min="-0.005" :max="0.005" :step="0.00005" snap @change="patch({ z })" />
      </div>

      <q-separator />

      <!-- aperture_diameter -->
      <q-input
        v-model.number="apertureDiameter"
        label="Aperture diameter (px, -1=auto)"
        type="number"
        dense
        outlined
        filled
        stack-label
        :debounce="600"
        @update:model-value="patch({ aperture_diameter: apertureDiameter })"
      />

      <!-- bessel_inner_fraction: always visible, disabled when not bessel -->
      <div>
        <div class="row items-center q-gutter-x-sm">
          <div class="col text-caption" :class="beamType === 'bessel' ? 'text-grey-7' : 'text-grey-4'">
            Bessel inner fraction
          </div>
          <div class="col-auto text-caption" :class="beamType !== 'bessel' ? 'text-grey-4' : ''">
            {{ besselInnerFraction.toFixed(2) }}
          </div>
        </div>
        <div style="position: relative">
          <q-slider
            v-model="besselInnerFraction"
            :min="0"
            :max="0.99"
            :step="0.01"
            snap
            :disable="beamType !== 'bessel'"
            @change="patch({ bessel_inner_fraction: besselInnerFraction })"
          />
          <!-- Transparent overlay captures hover when slider is disabled -->
          <div
            v-if="beamType !== 'bessel'"
            style="position: absolute; inset: 0; cursor: not-allowed"
          >
            <q-tooltip>Only applicable for Bessel beam type</q-tooltip>
          </div>
        </div>
      </div>

      <q-separator />

      <!-- Pattern offset -->
      <div class="row q-gutter-x-sm">
        <q-input
          v-model.number="offsetH"
          label="Offset H (px)"
          type="number"
          dense
          outlined
          filled
          stack-label
          class="col"
          :debounce="600"
          @update:model-value="patch({ offset_h: offsetH })"
        />
        <q-input
          v-model.number="offsetV"
          label="Offset V (px)"
          type="number"
          dense
          outlined
          filled
          stack-label
          class="col"
          :debounce="600"
          @update:model-value="patch({ offset_v: offsetV })"
        />
      </div>

      <q-separator />

      <!-- Auto-update toggle + manual update button -->
      <div class="row items-center q-gutter-x-sm">
        <q-toggle v-model="autoUpdate" label="Auto update" @update:model-value="patch({ auto_update: autoUpdate })" />
        <q-space />
        <q-btn
          v-if="!autoUpdate"
          dense
          unelevated
          color="primary"
          label="Update"
          icon="refresh"
          @click="slm.triggerUpdate()"
        />
      </div>

    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
  import { ref, watch } from 'vue'
  import { useSlmStore } from 'stores/slm'
  import type { TrapState } from 'src/api/slm'

  const slm = useSlmStore()

  const x = ref(0)
  const y = ref(0)
  const z = ref(0)
  const beamType = ref('gauss')
  const apertureDiameter = ref(0)
  const besselInnerFraction = ref(0.9)
  const offsetH = ref(0)
  const offsetV = ref(0)
  const autoUpdate = ref(true)

  watch(
    () => slm.device?.state.trap,
    (trap) => {
      if (!trap) return
      x.value = trap.x
      y.value = trap.y
      z.value = trap.z
      beamType.value = trap.beam_type
      apertureDiameter.value = trap.aperture_diameter
      besselInnerFraction.value = trap.bessel_inner_fraction
      offsetH.value = trap.offset_h
      offsetV.value = trap.offset_v
      autoUpdate.value = trap.auto_update
    },
    { immediate: true }
  )

  async function patch(props: Partial<TrapState>) {
    await slm.patchTrap(props)
  }

  async function zero(axis: 'x' | 'y' | 'z') {
    if (axis === 'x') x.value = 0
    else if (axis === 'y') y.value = 0
    else z.value = 0
    await patch({ [axis]: 0 })
  }
</script>
