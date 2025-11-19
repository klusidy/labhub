<!-- src/components/PropertiesCard.vue -->
<template>
  <q-card flat bordered class="q-pa-sm q-ma-md">
    <q-card-section class="text-subtitle2 q-py-xs q-px-sm">Properties</q-card-section>
    <q-separator />

    <div class="q-pa-xs">
      <!-- <div v-for="p in rows" :key="p.key" class="row items-center q-col-gutter-sm q-py-xs"> -->
      <div class="row q-col-gutter-sm q-pa-sm">
        <div v-for="p in rows" :key="p.key" class="col-12 col-sm-6">
          <div class="col-6 col-sm-6">
            <q-input
              v-model="p.requested"
              :ref="(comp) => (fieldEls[p.key] = (comp as any)?.$el ?? (comp as any) ?? null)"
              :label="p.label"
              stack-label
              dense
              outlined
              filled
              type="number"
              :inputmode="'decimal'"
              :suffix="p.unit || ''"
              :debounce="1000"
              :readonly="p.readonly || false"
              :disable="p.readonly || false"
              @update:model-value="onRowChange(p)"
              :class="{ 'prop-updated': p.justUpdated }"
            >
              <q-tooltip v-if="p.hint">
                {{ p.hint }}
              </q-tooltip>
            </q-input>
          </div>
        </div>
      </div>
    </div>
  </q-card>
</template>

<script setup lang="ts">
  import { reactive, watch, nextTick, ref } from 'vue'
  import { usePicoscopeStore } from 'stores/picoscope'
  import type { QInput } from 'quasar' // if you want typing

  const fieldEls = ref<Record<string, HTMLElement | null>>({})
  const ps = usePicoscopeStore()

  function labelFromName(name: string): string {
    return name.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
  }

  type NumberRow = {
    key: string
    label: string
    unit?: string | undefined
    hint?: string | undefined
    requested: number
    actual?: number
    readonly?: boolean

    justUpdated?: boolean
  }

  const rows = reactive<NumberRow[]>([])

  watch(
    () => [ps.spec?.properties, ps.device?.state] as const,
    ([props, state]) => {
      if (!props || !state) return

      // clear existing rows
      rows.splice(0, rows.length)

      for (const p of props) {
        const name = p.name
        const value = state[name] as number | undefined

        rows.push({
          key: name,
          label: labelFromName(name),
          unit: p.unit ?? undefined,
          hint: p.doc ?? undefined,
          requested: value ?? (p.default as number | null) ?? 0,
          readonly: p.read_only,
        })
      }
    },
    { immediate: true }
  )

  async function onRowChange(row: NumberRow) {
    if (row.readonly) return
    const key = row.key
    const value = row.requested

    try {
      await ps.patchProps({ [key]: value })
      highlightField(key)
    } catch (e) {
      console.error('patchProps failed:', e)
    }
  }

  function highlightField(key: string) {
    const el = fieldEls.value[key]
    if (!el) return

    el.classList.add('prop-updated')
    setTimeout(() => {
      el.classList.remove('prop-updated')
    }, 600)
  }

  // async function onRowChange(row: NumberRow) {
  //   if (row.readonly) return
  //   const key = row.key

  //   await ps.patchProps({ [row.key]: row.requested }) // new
  //   ps.last_patched_property.valueOf = key

  //   current.justUpdated = true // will be reseted to false with the next update
  //   console.log('Property updated:', key, '->', row.requested)
  //   // setTimeout(() => {
  //   //   row.justUpdated = false
  //   // }, 400)
  // }
</script>

<style scoped>
  /* .prop-updated {
    animation: propUpdatedPulse 0.4s ease-out;
    border: 10px solid lime;
  }

  @keyframes propUpdatedPulse {
    0% {
      box-shadow: 0 0 0 0 rgba(76, 175, 80, 0.7);
    }
    100% {
      box-shadow: 0 0 0 6px rgba(76, 175, 80, 0);
    }
  } */
  :deep(.q-input.prop-updated .q-field__control) {
    position: relative;
  }

  /* Animated bottom line */
  :deep(.q-input.prop-updated .q-field__control::after) {
    content: '';
    position: absolute;
    left: 50%;
    bottom: 0;
    height: 2px;
    width: 100%;
    transform-origin: center;
    transform: translateX(-50%) scaleX(0);
    background: var(--q-primary);
    animation: q-input-confirm 600ms ease-out forwards;
  }

  /* Label color “success flash” */
  :deep(.q-input.prop-updated .q-field__label) {
    /*color: var(--q-positive);*/
    transition: color 400ms;
  }

  @keyframes q-input-confirm {
    0% {
      transform: translateX(-50%) scaleX(0);
      background: var(--q-primary);
    }
    50% {
      transform: translateX(-50%) scaleX(1);
      background: var(--q-positive); /* green */
    }
    100% {
      transform: translateX(-50%) scaleX(1);
      background: var(--q-primary);
    }
  }
</style>
