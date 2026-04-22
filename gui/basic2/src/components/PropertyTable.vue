<template>
  <q-card flat bordered class="property-table">
    <q-card-section class="q-pa-none">
      <q-markup-table flat dense wrap-cells class="property-markup-table">
        <thead class="bg-light-blue-10 text-white" style="line-height: 30px">
          <tr>
            <th class="text-left">Name</th>
            <th class="text-left" style="width: 80px">Type</th>
            <th class="text-left" style="width: 150px">Current</th>
            <th class="text-left" style="width: 150px">New Value</th>
            <th style="width: 40px"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="prop in properties" :key="prop.name" class="property-row">
            <td class="text-weight-medium">
              <div class="row items-center no-wrap">
                <q-icon
                  v-if="prop.read_only"
                  name="lock"
                  size="sm"
                  color="grey-6"
                  class="q-mr-xs"
                />
                <span>{{ prop.name }}</span>
              </div>
              <div v-if="prop.doc" class="text-caption text-grey-6 prop-doc">
                {{ prop.doc }}
              </div>
            </td>
            <td class="text-caption text-grey-7">{{ inferType(prop) }}</td>
            <td>
              <code class="current-value">{{
                formatValue(deviceState?.[prop.name], prop.unit)
              }}</code>
            </td>
            <td>
              <PropertyInput
                v-if="!prop.read_only && !disabled"
                :property="prop"
                :value="deviceState?.[prop.name]"
                @update="(val) => onUpdate(prop.name, val)"
              />
            </td>
            <td>
              <q-btn
                flat
                dense
                round
                icon="drag_indicator"
                size="sm"
                color="grey"
                draggable="true"
                @dragstart="(e: DragEvent) => onDragStart(e, prop)"
              >
                <q-tooltip>Drag to shelf</q-tooltip>
              </q-btn>
            </td>
          </tr>
        </tbody>
      </q-markup-table>

      <div v-if="properties.length === 0" class="text-grey q-pa-sm">No properties available</div>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useDevicesStore } from 'stores/devices';
import { formatValue, inferType } from 'src/utils/formatter';
import PropertyInput from './PropertyInput.vue';
import type { PropertySpec } from 'src/api/devices';

const props = defineProps<{
  deviceId: string;
  filterProp?: string; // If provided, only show this property
}>();

const store = useDevicesStore();

const spec = computed(() => store.getSpecForPath(props.deviceId));
const deviceState = computed(() => store.getStateForPath(props.deviceId));

const disabled = computed(() => {
  const rootId = props.deviceId.split('/')[0];
  return store.devices.find((d) => d.id === rootId)?.status !== 'connected';
});

const properties = computed(() => {
  const all = spec.value?.properties || [];
  if (props.filterProp) {
    return all.filter((p) => p.name === props.filterProp);
  }
  return all;
});

async function onUpdate(propName: string, value: unknown) {
  try {
    await store.updateProperty(props.deviceId, propName, value);
  } catch (e) {
    console.error('Failed to update property:', e);
  }
}

function onDragStart(e: DragEvent, prop: PropertySpec) {
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'copy';
    e.dataTransfer.setData(
      'application/json',
      JSON.stringify({
        type: 'property',
        deviceId: props.deviceId,
        itemName: prop.name,
      }),
    );
  }
}
</script>

<style scoped>
.property-table {
  margin-bottom: 12px;
}

.property-markup-table :deep(thead th) {
  padding: 6px 8px;
  font-weight: 500;
}

.property-markup-table :deep(tbody td) {
  padding: 4px 8px;
}

.property-row:hover {
  background-color: #f5f5f5;
}

.current-value {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 4px;
  display: inline-block;
  min-width: 100px;
  text-align: right;
}

.prop-doc {
  font-size: 11px;
  line-height: 1.3;
  margin-top: 2px;
  overflow: hidden;
  font-style: italic;
  text-overflow: ellipsis;
}
</style>
