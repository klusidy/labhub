<template>
  <q-page class="row no-wrap">
    <!-- Left sidebar: Device list -->
    <div class="device-list-sidebar q-pa-sm">
      <q-list separator>
        <q-item
          v-for="device in store.devices"
          :key="device.id"
          clickable
          :active="store.selectedDeviceId === device.id"
          active-class="bg-green-2"
          @click="store.selectDevice(device.id)"
        >
          <q-item-section avatar>
            <q-icon
              :name="getStatusIcon(device.id)"
              :color="getStatusColor(device.id)"
            />
          </q-item-section>
          <q-item-section>
            <q-item-label>
              {{ device.id }}
              <q-badge
                v-if="store.hasUnsavedChanges(device.id)"
                color="orange"
                class="q-ml-xs"
              >
                *
              </q-badge>
            </q-item-label>
            <q-item-label caption>{{ device.driver }}</q-item-label>
          </q-item-section>
        </q-item>
      </q-list>

      <!-- Add device button -->
      <q-btn
        flat
        dense
        color="primary"
        icon="add"
        label="Add Device"
        class="full-width q-mt-md"
        @click="showAddDeviceDialog"
      />

      <!-- Additional Config button -->
      <q-btn
        flat
        dense
        color="secondary"
        icon="tune"
        label="Additional Config"
        class="full-width q-mt-sm"
        @click="store.selectDevice(null)"
      />
    </div>

    <!-- Main content: Device editor -->
    <div class="device-editor-main col q-pa-md">
      <template v-if="store.selectedDevice">
        <DeviceEditor
          :device="store.selectedDevice"
          :device-state="store.selectedDeviceState"
          :drivers="store.drivers"
          @update="onDeviceUpdate"
          @save="onSaveDevice"
          @connect="onConnectDevice"
          @disconnect="onDisconnectDevice"
          @delete="onDeleteDevice"
        />
      </template>
      <template v-else>
        <!-- Additional Config editor (shown when no device selected) -->
        <div class="additional-config-editor">
          <div class="text-h5 q-mb-md">Additional Config</div>
          <div class="text-caption text-grey-7 q-mb-md">
            Extra configuration in YAML format (e.g., InfluxDB settings)
          </div>
          <q-input
            v-model="additionalConfigYaml"
            type="textarea"
            outlined
            dense
            :rows="15"
            class="additional-config-textarea q-mb-md"
            placeholder="# Example:
influx:
  enabled: true
  url: http://localhost:8086
  token: your-token
  org: your-org
  bucket: labhub"
            :error="!!additionalConfigError"
            :error-message="additionalConfigError ?? undefined"
            @update:model-value="onAdditionalConfigChange"
          />
          <div class="row items-center q-gutter-sm">
            <q-btn
              color="primary"
              icon="save"
              label="Save"
              :loading="store.loading"
              :disable="!store.additionalConfigChanged || !!additionalConfigError"
              @click="onSaveAdditionalConfig"
            />
            <q-badge
              v-if="store.additionalConfigChanged"
              color="orange"
            >
              unsaved changes
            </q-badge>
          </div>
        </div>
      </template>
    </div>

    <!-- Add device dialog -->
    <q-dialog v-model="addDeviceDialogOpen">
      <q-card style="min-width: 450px">
        <q-card-section>
          <div class="text-h6">Add New Device</div>
        </q-card-section>

        <q-card-section>
          <q-input
            v-model="newDeviceId"
            label="Device ID"
            hint="Unique identifier for this device"
            :rules="[(v: string) => !!v || 'Required', (v: string) => !deviceIdExists(v) || 'ID already exists']"
          />

          <div class="row q-col-gutter-md q-mt-md">
            <div class="col-6">
              <q-select
                v-model="newDeviceVendor"
                label="Vendor"
                :options="vendorOptions"
                outlined
                dense
                emit-value
                map-options
                @update:model-value="onNewVendorChange"
              />
            </div>
            <div class="col-6">
              <q-select
                v-model="newDeviceDriver"
                label="Device"
                :options="newDeviceOptions"
                option-value="id"
                option-label="name"
                outlined
                dense
                emit-value
                map-options
                :disable="!newDeviceVendor"
              />
            </div>
          </div>
        </q-card-section>

        <q-card-actions align="right">
          <q-btn flat label="Cancel" v-close-popup />
          <q-btn
            color="primary"
            label="Add"
            :disable="!newDeviceId || !newDeviceDriver || deviceIdExists(newDeviceId)"
            @click="addDevice"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useQuasar } from 'quasar';
import yaml from 'js-yaml';
import { useConfigStore } from 'stores/config';
import type { DeviceConfig } from 'src/api/admin';
import DeviceEditor from 'components/DeviceEditor.vue';

const $q = useQuasar();
const store = useConfigStore();

// Add device dialog state
const addDeviceDialogOpen = ref(false);
const newDeviceId = ref('');
const newDeviceVendor = ref<string | null>(null);
const newDeviceDriver = ref('');

// Additional config state
const additionalConfigYaml = ref('');
const additionalConfigError = ref<string | null>(null);

// Convert influx config to YAML string
function influxToYaml(influx: Record<string, unknown> | undefined): string {
  if (!influx || Object.keys(influx).length === 0) return '';
  try {
    return yaml.dump({ influx }, { indent: 2, lineWidth: -1 });
  } catch {
    return '';
  }
}

// Parse YAML to config object (extracts influx key)
function yamlToInflux(yamlStr: string): Record<string, unknown> | undefined {
  if (!yamlStr.trim()) return undefined;
  const parsed = yaml.load(yamlStr) as Record<string, unknown> | null;
  if (!parsed) return undefined;
  // Extract influx key if present, otherwise treat the whole thing as influx config
  if ('influx' in parsed) {
    return parsed.influx as Record<string, unknown>;
  }
  return parsed;
}

// Watch for store.influx changes to update the textarea
watch(
  () => store.influx,
  (newInflux) => {
    additionalConfigYaml.value = influxToYaml(newInflux);
    additionalConfigError.value = null;
  },
  { immediate: true }
);

function onAdditionalConfigChange() {
  try {
    const parsed = yamlToInflux(additionalConfigYaml.value);
    additionalConfigError.value = null;
    store.updateAdditionalConfig(parsed);
  } catch (e) {
    additionalConfigError.value = e instanceof Error ? e.message : 'Invalid YAML';
  }
}

async function onSaveAdditionalConfig() {
  try {
    await store.saveAdditionalConfig();
    $q.notify({ type: 'positive', message: 'Additional config saved' });
  } catch (e) {
    $q.notify({
      type: 'negative',
      message: `Failed to save: ${e instanceof Error ? e.message : String(e)}`,
    });
  }
}

// Get unique vendors from drivers
const vendorOptions = computed(() => {
  const vendors = new Set(store.drivers.map((d) => d.vendor));
  return Array.from(vendors).sort().map((v) => ({ label: v, value: v }));
});

// Get devices filtered by selected vendor for new device dialog
const newDeviceOptions = computed(() => {
  if (!newDeviceVendor.value) return [];
  return store.drivers
    .filter((d) => d.vendor === newDeviceVendor.value)
    .sort((a, b) => a.name.localeCompare(b.name));
});

function onNewVendorChange() {
  newDeviceDriver.value = '';
}

function deviceIdExists(id: string): boolean {
  return store.devices.some((d: DeviceConfig) => d.id === id);
}

function getStatusIcon(devId: string): string {
  const status = store.getDeviceStatus(devId);
  switch (status) {
    case 'connected':
      return 'check_circle';
    case 'disconnected':
      return 'cancel';
    case 'unhealthy':
      return 'warning';
    default:
      return 'help_outline';
  }
}

function getStatusColor(devId: string): string {
  const status = store.getDeviceStatus(devId);
  switch (status) {
    case 'connected':
      return 'green-10';
    case 'disconnected':
      return 'negative';
    case 'unhealthy':
      return 'warning';
    default:
      return 'grey';
  }
}

function showAddDeviceDialog() {
  newDeviceId.value = '';
  newDeviceVendor.value = null;
  newDeviceDriver.value = '';
  addDeviceDialogOpen.value = true;
}

function addDevice() {
  store.addDevice(newDeviceId.value, newDeviceDriver.value);
  addDeviceDialogOpen.value = false;
}

function onDeviceUpdate(config: DeviceConfig) {
  // Use the ORIGINAL device ID from the store (selected device), not the potentially-changed config.id
  const originalId = store.selectedDeviceId;
  if (originalId) {
    store.updateDeviceLocally(originalId, config);
  }
}

async function onSaveDevice(devId: string) {
  try {
    await store.saveDevice(devId);
    $q.notify({ type: 'positive', message: `Device '${devId}' saved` });
  } catch (e) {
    $q.notify({
      type: 'negative',
      message: `Failed to save: ${e instanceof Error ? e.message : String(e)}`,
    });
  }
}

async function onConnectDevice(devId: string) {
  try {
    await store.connectDevice(devId);
    $q.notify({ type: 'positive', message: `Device '${devId}' connected` });
  } catch (e) {
    $q.notify({
      type: 'negative',
      message: `Failed to connect: ${e instanceof Error ? e.message : String(e)}`,
    });
  }
}

async function onDisconnectDevice(devId: string) {
  try {
    await store.disconnectDevice(devId);
    $q.notify({ type: 'positive', message: `Device '${devId}' disconnected` });
  } catch (e) {
    $q.notify({
      type: 'negative',
      message: `Failed to disconnect: ${e instanceof Error ? e.message : String(e)}`,
    });
  }
}

function onDeleteDevice(devId: string) {
  $q.dialog({
    title: 'Remove Device',
    message: `Are you sure you want to remove '${devId}' from the configuration?`,
    cancel: true,
    persistent: true,
  }).onOk(() => {
    store.deleteDevice(devId)
      .then(() => {
        $q.notify({ type: 'positive', message: `Device '${devId}' removed` });
      })
      .catch((e: unknown) => {
        $q.notify({
          type: 'negative',
          message: `Failed to remove: ${e instanceof Error ? e.message : String(e)}`,
        });
      });
  });
}

onMounted(async () => {
  await Promise.all([
    store.loadConfig(),
    store.loadDrivers(),
    store.loadDeviceStates(),
  ]);

  // Initialize additional config YAML from loaded config
  additionalConfigYaml.value = influxToYaml(store.influx);

  // Select first device if none selected
  const firstDevice = store.devices[0];
  if (!store.selectedDeviceId && firstDevice) {
    store.selectDevice(firstDevice.id);
  }
});
</script>

<style scoped>
.device-list-sidebar {
  width: 250px;
  min-width: 200px;
  max-width: 300px;
  border-right: 1px solid #e0e0e0;
  overflow-y: auto;
}

.device-editor-main {
  overflow-y: auto;
}

.additional-config-textarea :deep(textarea) {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}

.additional-config-editor {
  max-width: 700px;
}
</style>
