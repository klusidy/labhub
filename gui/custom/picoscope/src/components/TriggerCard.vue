<!-- src/components/TriggerCard.vue -->
<template>
  <q-card flat bordered class="q-pa-sm q-ma-md">
    <q-card-section class="text-subtitle2 q-py-xs q-px-sm row items-center">
      Trigger

      <q-toggle
        v-model="trigger.enable"
        dense
        checked-icon="check"
        unchecked-icon="clear"
        size="xl"
        class="q-ml-auto"
        @update:model-value="applyTriggerUpdate()"
      >
        <q-tooltip> Enable/disable trigger </q-tooltip>
      </q-toggle>
    </q-card-section>
    <q-separator />

    <div class="q-pa-sm">
      <!-- Row 1: enable, channel, threshold, edge -->
      <div class="row q-col-gutter-sm q-pb-sm items-center">
        <div class="col-5 col-sm-5">
          <q-btn-toggle
            v-model="trigger.channel"
            :options="
              channelOptions.map((ch: string) => ({
                label: ch,
                value: ch,
              }))
            "
            :toggle-color="
              trigger.channel == 'A'
                ? 'blue'
                : trigger.channel == 'B'
                  ? 'red'
                  : trigger.channel == 'C'
                    ? 'green'
                    : trigger.channel == 'D'
                      ? 'amber'
                      : 'grey'
            "
            dense
            outlined
            filled
            spread
            @update:model-value="applyTriggerUpdate()"
          >
            <q-tooltip> Source channel for trigger </q-tooltip>
          </q-btn-toggle>
        </div>

        <div class="col-3 col-sm-3">
          <q-btn-toggle
            v-model="trigger.edge"
            :options="edgeOptions"
            dense
            outlined
            filled
            spread
            padding:5px
            @update:model-value="applyTriggerUpdate()"
          >
            <q-tooltip> Edge type: Rising, Falling, or Both </q-tooltip>
          </q-btn-toggle>
        </div>

        <div class="col-4 col-sm-4">
          <q-input
            v-model.number="trigger.delaySamples"
            label="Delay"
            suffix="#"
            stack-label
            dense
            outlined
            filled
            type="number"
            inputmode="decimal"
            :debounce="150"
            @update:model-value="applyTriggerUpdate()"
          />
        </div>
      </div>

      <!-- Row 2 -->

      <div class="row q-col-gutter-sm q-pt-xs">
        <div class="col-6 col-sm-6">
          <q-input
            v-model.number="trigger.thresholdMv"
            label="Threshold"
            stack-label
            dense
            outlined
            filled
            type="number"
            inputmode="decimal"
            suffix="mV"
            :debounce="150"
            @update:model-value="applyTriggerUpdate()"
          />
        </div>

        <div class="col-6 col-sm-6">
          <q-input
            v-model.number="trigger.autoTriggerMs"
            label="Auto trigger"
            suffix="ms"
            stack-label
            dense
            outlined
            filled
            type="number"
            inputmode="decimal"
            :debounce="150"
            @update:model-value="applyTriggerUpdate()"
          />
        </div>
      </div>
    </div>
  </q-card>
</template>

<script setup lang="ts">
  import { computed, reactive, watch } from 'vue'
  import { debounce } from 'lodash-es'
  import { usePicoscopeStore } from 'stores/picoscope'
  import type { HwChannelId } from 'src/api/picoscope'

  type Edge = 'RISING' | 'FALLING' | 'RISING_OR_FALLING'

  interface TriggerState {
    enable: boolean
    channel: string
    thresholdMv: number
    edge: Edge
    delaySamples: number
    autoTriggerMs: number
  }

  const trigger = reactive<TriggerState>({
    enable: false,
    channel: 'A',
    thresholdMv: 500,
    edge: 'RISING',
    delaySamples: 0,
    autoTriggerMs: 1000,
  })

  const channelOptions = ['A', 'B', 'C', 'D']

  const edgeOptions = [
    { label: '↗', value: 'RISING' as Edge },
    { label: '⤮', value: 'RISING_OR_FALLING' as Edge },
    { label: '↘', value: 'FALLING' as Edge },
  ]

  // synchronize backend -> local UI state

  const ps = usePicoscopeStore()

  watch(
    () => ps.trigger(),
    (raw) => {
      if (!raw || Object.keys(raw).length === 0) {
        trigger.enable = false
        trigger.channel = 'A'
        trigger.thresholdMv = 0.0
        trigger.edge = 'RISING_OR_FALLING'
        trigger.delaySamples = 0
        trigger.autoTriggerMs = 1000
      } else {
        trigger.enable = 1 === raw.enable
        trigger.channel = raw.source_str
        trigger.thresholdMv = raw.threshold_mV
        trigger.edge = raw.direction_str as Edge
        trigger.delaySamples = raw.delay
        trigger.autoTriggerMs = raw.auto_trigger_ms
      }
    },
    { immediate: true }
  )

  import { toRaw } from 'vue'
  function applyTriggerUpdate() {
    // snapshot current UI state
    void debouncedTriggerUpdate({ ...toRaw(trigger) })
  }

  const debouncedTriggerUpdate = debounce(async (v: typeof trigger) => {
    await ps.setTriggerSimple({
      enable: v.enable,
      source: v.channel as HwChannelId,
      threshold_mV: v.thresholdMv,
      direction: v.edge,
      delay: v.delaySamples,
      auto_trigger_ms: v.autoTriggerMs,
    })
  }, 200)
</script>
