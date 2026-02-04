<template>
  <div class="device-editor">
    <!-- Header with device name and status -->
    <div class="row items-center q-mb-md">
      <div class="text-h5 q-mr-md">{{ localDevice.id }}</div>
      <q-chip
        :color="statusColor"
        text-color="white"
        :icon="statusIcon"
        size="sm"
      >
        {{ deviceState?.status || 'unknown' }}
      </q-chip>
    </div>

    <!-- Device ID (read-only, set when creating device) -->
    <q-input
      v-model="localDevice.id"
      label="Device ID"
      outlined
      dense
      readonly
      class="q-mb-md"
      hint="Set when creating device (cannot be changed)"
    />

    <!-- Driver selection: Vendor + Device -->
    <div class="row q-col-gutter-md q-mb-md">
      <div class="col-6">
        <q-select
          v-model="selectedVendor"
          label="Vendor"
          :options="vendorOptions"
          outlined
          dense
          emit-value
          map-options
          @update:model-value="onVendorChange"
        />
      </div>
      <div class="col-6">
        <q-select
          v-model="selectedDevice"
          label="Device"
          :options="deviceOptions"
          option-value="id"
          option-label="name"
          outlined
          dense
          emit-value
          map-options
          :disable="!selectedVendor"
          @update:model-value="onDeviceChange"
        >
          <template v-slot:option="{ opt, itemProps }">
            <q-item v-bind="itemProps">
              <q-item-section>
                <q-item-label>{{ opt.name }}</q-item-label>
              </q-item-section>
            </q-item>
          </template>
        </q-select>
      </div>
    </div>

    <!-- Config YAML editor -->
    <div class="text-subtitle2 q-mb-xs">Additional Options (YAML)</div>
    <q-input
      v-model="optionsYaml"
      type="textarea"
      outlined
      dense
      :rows="12"
      class="config-textarea q-mb-md"
      hint="Device-specific options in YAML format"
      :error="!!yamlError"
      :error-message="yamlError ?? undefined"
      @update:model-value="onYamlChange"
    />

    <!-- Action buttons -->
    <div class="row q-gutter-sm">
      <q-btn
        color="primary"
        icon="save"
        label="Save"
        :loading="saving"
        @click="$emit('save', localDevice.id)"
      />
      <q-btn
        color="secondary"
        icon="refresh"
        label="Reload"
        :loading="reloading"
        @click="$emit('reload', localDevice.id)"
      >
        <q-tooltip>Save config and reload device</q-tooltip>
      </q-btn>
      <q-space />
      <q-btn
        color="negative"
        icon="delete"
        label="Delete"
        @click="$emit('delete', localDevice.id)"
      />
    </div>

    <!-- Device state info (if connected) -->
    <template v-if="deviceState?.state && Object.keys(deviceState.state).length">
      <q-separator class="q-my-md" />
      <div class="text-subtitle2 q-mb-sm">Current State</div>
      <div class="state-display">
        <pre>{{ JSON.stringify(deviceState.state, null, 2) }}</pre>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import yaml from 'js-yaml';
import type { DeviceConfig, DriverInfo, DeviceState } from 'src/api/admin';

const props = defineProps<{
  device: DeviceConfig;
  deviceState: DeviceState | null;
  drivers: DriverInfo[];
}>();

const emit = defineEmits<{
  (e: 'update', config: DeviceConfig): void;
  (e: 'save', devId: string): void;
  (e: 'reload', devId: string): void;
  (e: 'delete', devId: string): void;
}>();

const saving = ref(false);
const reloading = ref(false);
const yamlError = ref<string | null>(null);

// Local copy of device for editing
const localDevice = ref<DeviceConfig>({ ...props.device });

// Extract options (everything except id and driver) as YAML
const optionsYaml = ref('');

// Selected vendor and device for the split dropdown
const selectedVendor = ref<string | null>(null);
const selectedDevice = ref<string | null>(null);

// Get unique vendors from drivers
const vendorOptions = computed(() => {
  const vendors = new Set(props.drivers.map((d) => d.vendor));
  return Array.from(vendors).sort().map((v) => ({ label: v, value: v }));
});

// Get devices filtered by selected vendor
const deviceOptions = computed(() => {
  if (!selectedVendor.value) return [];
  return props.drivers
    .filter((d) => d.vendor === selectedVendor.value)
    .sort((a, b) => a.name.localeCompare(b.name));
});

const statusColor = computed(() => {
  switch (props.deviceState?.status) {
    case 'connected':
      return 'green-10';
    case 'disconnected':
      return 'negative';
    case 'unhealthy':
      return 'warning';
    default:
      return 'grey';
  }
});

const statusIcon = computed(() => {
  switch (props.deviceState?.status) {
    case 'connected':
      return 'check_circle';
    case 'disconnected':
      return 'cancel';
    case 'unhealthy':
      return 'warning';
    default:
      return 'help_outline';
  }
});

function deviceToYaml(device: DeviceConfig): string {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { id, driver, ...options } = device;
  if (Object.keys(options).length === 0) return '';
  try {
    return yaml.dump(options, { indent: 2, lineWidth: -1 });
  } catch {
    return '';
  }
}

function yamlToOptions(yamlStr: string): Record<string, unknown> {
  if (!yamlStr.trim()) return {};
  return (yaml.load(yamlStr) as Record<string, unknown>) || {};
}

function parseDriverId(driverId: string): { vendor: string; device: string } | null {
  const parts = driverId.split('.');
  if (parts.length >= 2 && parts[0]) {
    return { vendor: parts[0], device: parts.slice(1).join('.') };
  }
  return null;
}

function updateLocalFromProps() {
  localDevice.value = { ...props.device };
  optionsYaml.value = deviceToYaml(props.device);
  yamlError.value = null;

  // Parse driver into vendor + device
  const parsed = parseDriverId(props.device.driver);
  if (parsed) {
    selectedVendor.value = parsed.vendor;
    // Find the matching driver ID
    const matchingDriver = props.drivers.find((d) => d.id === props.device.driver);
    selectedDevice.value = matchingDriver?.id || null;
  } else {
    selectedVendor.value = null;
    selectedDevice.value = null;
  }
}

function onVendorChange() {
  // Reset device selection when vendor changes
  selectedDevice.value = null;
  // Clear driver in local device
  localDevice.value.driver = '';
  emitUpdate();
}

function onDeviceChange() {
  if (selectedDevice.value) {
    localDevice.value.driver = selectedDevice.value;
    emitUpdate();
  }
}

function onYamlChange() {
  try {
    const options = yamlToOptions(optionsYaml.value);
    yamlError.value = null;
    localDevice.value = {
      id: localDevice.value.id,
      driver: localDevice.value.driver,
      ...options,
    };
    emitUpdate();
  } catch (e) {
    yamlError.value = e instanceof Error ? e.message : 'Invalid YAML';
  }
}

function emitUpdate() {
  emit('update', { ...localDevice.value });
}

// Watch for prop changes
watch(
  () => props.device,
  () => {
    updateLocalFromProps();
  },
  { immediate: true, deep: true }
);
</script>

<style scoped>
.device-editor {
  max-width: 800px;
}

.config-textarea :deep(textarea) {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}

.state-display {
  background: #f5f5f5;
  border-radius: 4px;
  padding: 8px;
  max-height: 200px;
  overflow: auto;
}

.state-display pre {
  margin: 0;
  font-size: 12px;
}
</style>
