<template>
  <div class="shelf column no-wrap" style="overflow-y: auto">
    <div v-if="!cs.pinnedVars.length" class="empty-shelf column items-center justify-center q-pa-lg">
      <q-icon name="push_pin" size="32px" color="grey-7" />
      <div class="text-caption text-grey-7 text-center q-mt-sm">
        Pin variables here from any module's detail panel
      </div>
    </div>

    <div v-else class="q-pa-sm column q-gutter-sm">
      <div
        v-for="pin in cs.pinnedVars"
        :key="pin.id"
        class="shelf-item q-pa-sm rounded-borders"
      >
        <div class="row items-start no-wrap">
          <div class="col column" style="min-width: 0">
            <div class="row items-baseline no-wrap q-mb-xs">
              <span class="text-caption text-grey-4 ellipsis" style="font-size: 10px">
                {{ pin.nodeLabel }}
              </span>
            </div>
            <div class="row items-baseline no-wrap">
              <span class="prop-key text-grey-6 ellipsis q-mr-xs" style="font-size: 10px">
                {{ pin.propLabel }}
              </span>
            </div>
            <div class="row items-baseline no-wrap q-mt-xs">
              <span class="value text-white" style="font-size: 13px; font-family: monospace">
                {{ formatValue(cs.getPinnedValue(pin)) }}
              </span>
              <span v-if="pin.unit" class="text-grey-6 q-ml-xs" style="font-size: 10px">
                {{ pin.unit }}
              </span>
            </div>
          </div>
          <q-btn
            flat
            round
            dense
            size="xs"
            icon="close"
            color="grey-7"
            @click="cs.unpinVariable(pin.id)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useChameleonStore } from 'stores/chameleon'

const cs = useChameleonStore()

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  if (typeof v === 'number') {
    if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(3) + 'M'
    if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(2) + 'k'
    return v.toFixed(3).replace(/\.?0+$/, '')
  }
  return String(v)
}
</script>

<style scoped>
.shelf {
  background: transparent;
}

.empty-shelf {
  flex: 1;
  min-height: 200px;
}

.shelf-item {
  background: #2b2b2b;
  border: 1px solid #3a3a3a;
}
</style>
