<template>
  <q-page class="device-page">
    <!-- No selection state -->
    <div v-if="!store.selectedNodeId && !macrosStore.selectedNodeId" class="no-selection">
      <q-icon name="touch_app" size="xl" color="grey-4" />
      <div class="text-h6 text-grey-6 q-mt-md">Select a device or macro</div>
      <div class="text-caption text-grey-5">
        Click on a device or macro in the tree to view details
      </div>
    </div>

    <!-- Macro function selected -->
    <div v-else-if="macrosStore.selectedFunction" class="q-pa-md">
      <div class="row items-center q-mb-md">
        <q-icon name="functions" color="pink-9" size="md" class="q-mr-sm" />
        <div>
          <div class="text-h5">{{ macrosStore.selectedFunction.func.name }}</div>
          <div class="text-caption text-grey-6">
            {{ macrosStore.selectedFunction.file.filename }}
          </div>
        </div>
      </div>
      <MacroPanel
        :filename="macrosStore.selectedFunction.file.filename"
        :filter-func="macrosStore.selectedFunction.func.name"
      />
    </div>

    <!-- Macro file selected (show editor + all functions) -->
    <div v-else-if="macrosStore.selectedFile" class="q-pa-md">
      <div class="row items-center q-mb-md">
        <q-icon name="description" color="primary" size="md" class="q-mr-sm" />
        <div class="col">
          <div class="text-h5">{{ macrosStore.selectedFile.filename }}</div>
          <div class="text-caption text-grey-6">
            {{ macrosStore.selectedFile.functions.length }} function(s)
            <span v-if="macrosStore.selectedFile.error" class="text-negative">
              &mdash; {{ macrosStore.selectedFile.error }}
            </span>
          </div>
        </div>
      </div>

      <!-- Functions in this file -->
      <MacroPanel
        v-if="macrosStore.selectedFile.functions.length > 0"
        :filename="macrosStore.selectedFile.filename"
        class="q-mb-md"
      />

      <!-- File editor -->
      <q-card flat bordered>
        <q-card-section class="q-py-sm">
          <div class="row items-center justify-between">
            <div class="text-subtitle2">Source Code</div>
            <div class="row q-gutter-sm">
              <q-badge
                v-if="macrosStore.fileContentDirty"
                color="warning"
                label="Unsaved changes"
              />
              <q-btn
                unelevated
                no-caps
                color="primary"
                label="Save"
                icon="save"
                padding="4px 16px"
                :loading="macrosStore.fileSaving"
                :disable="!macrosStore.fileContentDirty"
                @click="saveFile"
              />
            </div>
          </div>
        </q-card-section>
        <q-separator />
        <q-card-section class="q-pa-none">
          <q-input
            v-if="!macrosStore.fileContentLoading"
            :model-value="macrosStore.fileContent"
            type="textarea"
            outlined
            square
            :input-style="{
              fontFamily: 'Consolas, Monaco, monospace',
              fontSize: '13px',
              lineHeight: '1.5',
              minHeight: '300px',
            }"
            @update:model-value="(v) => macrosStore.updateFileContent(String(v))"
          />
          <div v-else class="q-pa-md text-center text-grey">
            <q-spinner size="sm" class="q-mr-xs" />
            Loading...
          </div>
        </q-card-section>
      </q-card>
    </div>

    <!-- Device selected (root or child) - show full device view -->
    <div v-else-if="(nodeType === 'device' || nodeType === 'childDevice') && selectedDevice" class="q-pa-md">
      <div class="row items-center q-mb-md">
        <q-icon
          :name="getStatusIcon(selectedDevice.status)"
          :color="getStatusColor(selectedDevice.status)"
          size="md"
          class="q-mr-sm"
        />
        <div>
          <div class="text-h5">{{ selectedDevicePath }}</div>
          <div class="text-caption text-grey-6">{{ selectedDevice.driver }}</div>
        </div>
        <q-btn
          v-if="nodeType === 'device'"
          flat
          dense
          round
          size="sm"
          icon="link_off"
          color="orange"
          class="q-ml-sm"
          @click="onDisconnect(selectedDevice.id)"
        >
          <q-tooltip>Disconnect</q-tooltip>
        </q-btn>
      </div>

      <div v-if="nodeType === 'device' && selectedDevice.doc" class="q-mb-md text-body2 text-grey-7">
        {{ selectedDevice.doc }}
      </div>

      <!-- All sections for device -->
      <DataSourcePanel v-if="hasDataSources" :device-id="selectedDevicePath!" />
      <PropertyTable v-if="hasProperties" :device-id="selectedDevicePath!" />
      <CommandPanel v-if="hasCommands" :device-id="selectedDevicePath!" />

      <!-- Child device sections -->
      <template
        v-if="selectedSpec?.children && Object.keys(selectedSpec.children).length > 0"
      >
        <template v-for="(childSpec, childId) in selectedSpec.children" :key="String(childId)">
          <q-separator class="q-my-md" />
          <div class="row items-center q-mb-sm">
            <q-icon name="device_hub" color="blue-grey-6" size="sm" class="q-mr-xs" />
            <span class="text-subtitle1 text-grey-7">{{ childId }}</span>
            <span v-if="childSpec.doc" class="text-caption text-grey-5 q-ml-sm"
              >— {{ childSpec.doc }}</span
            >
          </div>
          <DataSourcePanel
            v-if="(childSpec.data_sources?.length ?? 0) > 0"
            :device-id="`${selectedDevicePath}/${String(childId)}`"
          />
          <PropertyTable
            v-if="(childSpec.properties?.length ?? 0) > 0"
            :device-id="`${selectedDevicePath}/${String(childId)}`"
          />
          <CommandPanel
            v-if="(childSpec.commands?.length ?? 0) > 0"
            :device-id="`${selectedDevicePath}/${String(childId)}`"
          />
        </template>
      </template>
    </div>

    <!-- Disconnected device selected - show config panel -->
    <div v-else-if="nodeType === 'device' && selectedDisconnectedDevice" class="q-pa-md">
      <DeviceConfigPanel
        :device-config="selectedDisconnectedDevice"
        @save="onSaveDeviceConfig"
        @connect="onConnectDevice"
        @remove="onRemoveDevice"
      />
    </div>

    <!-- Category selected (properties/commands/dataSources) -->
    <div v-else-if="nodeType === 'category' && selectedDevice" class="q-pa-md">
      <div class="row items-center q-mb-md">
        <q-btn flat dense round icon="arrow_back" @click="store.selectNode(selectedDevicePath!)" />
        <div class="q-ml-sm">
          <div class="text-h6">{{ categoryTitle }}</div>
          <div class="text-caption text-grey-6">{{ selectedDevice.id }}</div>
        </div>
      </div>

      <DataSourcePanel v-if="categoryType === 'dataSources'" :device-id="selectedDevicePath!" />
      <PropertyTable v-if="categoryType === 'properties'" :device-id="selectedDevicePath!" />
      <CommandPanel v-if="categoryType === 'commands'" :device-id="selectedDevicePath!" />
    </div>

    <!-- Individual item selected (property/command/dataSource) -->
    <div v-else-if="nodeType && selectedDevice && itemName" class="q-pa-md">
      <div class="row items-center q-mb-md">
        <q-btn flat dense round icon="arrow_back" @click="goBackToCategory" />
        <div class="q-ml-sm">
          <div class="text-h6">{{ itemName }}</div>
          <div class="text-caption text-grey-6">{{ selectedDevice.id }} / {{ nodeType }}</div>
        </div>
      </div>
      <DataSourcePanel
        v-if="nodeType === 'dataSource'"
        :device-id="selectedDevicePath!"
        :filter-source="itemName"
      />
      <PropertyTable
        v-if="nodeType === 'property'"
        :device-id="selectedDevicePath!"
        :filter-prop="itemName"
      />
      <CommandPanel
        v-if="nodeType === 'command'"
        :device-id="selectedDevicePath!"
        :filter-cmd="itemName"
      />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useQuasar } from 'quasar';
import { useDevicesStore } from 'stores/devices';
import { useMacrosStore } from 'stores/macros';
import { useConfigStore } from 'stores/config';
import type { DeviceConfig } from '../api/admin';
import PropertyTable from 'components/PropertyTable.vue';
import CommandPanel from 'components/CommandPanel.vue';
import DataSourcePanel from 'components/DataSourcePanel.vue';
import MacroPanel from 'components/MacroPanel.vue';
import DeviceConfigPanel from 'components/DeviceConfigPanel.vue';

const $q = useQuasar();
const store = useDevicesStore();
const macrosStore = useMacrosStore();
const configStore = useConfigStore();

const selectedDevice = computed(() => store.selectedDevice);
const selectedDevicePath = computed(() => store.selectedDevicePath);
const selectedSpec = computed(() => store.selectedSpec);
const nodeType = computed(() => store.selectedNodeType);
const categoryType = computed(() => store.selectedCategoryType);
const itemName = computed(() => store.selectedItemName);

const hasProperties = computed(() => (selectedSpec.value?.properties?.length || 0) > 0);
const hasCommands = computed(() => (selectedSpec.value?.commands?.length || 0) > 0);
const hasDataSources = computed(() => (selectedSpec.value?.data_sources?.length || 0) > 0);

// Disconnected device: selectedNodeId is set, but no connected device matches
const selectedDisconnectedDevice = computed(() => {
  if (!store.selectedNodeId) return null;
  if (store.selectedDevice) return null; // it's a connected device
  // Only bare device IDs (no ':' separator) are device nodes
  if (store.selectedNodeId.includes(':')) return null;
  return configStore.getConfigDevice(store.selectedNodeId);
});

const categoryTitle = computed(() => {
  switch (categoryType.value) {
    case 'properties':
      return 'Properties';
    case 'commands':
      return 'Commands';
    case 'dataSources':
      return 'Data Sources';
    default:
      return '';
  }
});

function getStatusIcon(status: string): string {
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

function getStatusColor(status: string): string {
  switch (status) {
    case 'connected':
      return 'positive';
    case 'disconnected':
      return 'negative';
    case 'unhealthy':
      return 'warning';
    default:
      return 'grey';
  }
}

function goBackToCategory() {
  if (!selectedDevicePath.value || !nodeType.value) return;
  const catMap: Record<string, string> = {
    property: 'properties',
    command: 'commands',
    dataSource: 'dataSources',
  };
  const cat = catMap[nodeType.value];
  if (cat) {
    store.selectNode(`${selectedDevicePath.value}:${cat}`);
  } else {
    store.selectNode(selectedDevicePath.value);
  }
}

async function saveFile() {
  if (!macrosStore.selectedFile) return;
  try {
    await macrosStore.saveFileContent(macrosStore.selectedFile.filename);
    $q.notify({ type: 'positive', message: 'File saved', timeout: 1500 });
  } catch {
    $q.notify({ type: 'negative', message: 'Failed to save file' });
  }
}

function onDisconnect(devId: string) {
  store
    .disconnectDevice(devId)
    .then(() => {
      $q.notify({ type: 'positive', message: `Device '${devId}' disconnected` });
    })
    .catch((e: unknown) => {
      $q.notify({
        type: 'negative',
        message: `Failed to disconnect: ${e instanceof Error ? e.message : String(e)}`,
      });
    });
}

async function onSaveDeviceConfig(devId: string, config: DeviceConfig) {
  try {
    configStore.updateDeviceLocally(devId, config);
    await configStore.saveDevice(devId);
    $q.notify({ type: 'positive', message: `Device '${devId}' config saved` });
  } catch (e: unknown) {
    $q.notify({
      type: 'negative',
      message: `Failed to save: ${e instanceof Error ? e.message : String(e)}`,
    });
  }
}

function onConnectDevice(devId: string) {
  store
    .connectDevice(devId)
    .then(() => {
      $q.notify({ type: 'positive', message: `Device '${devId}' connected` });
    })
    .catch((e: unknown) => {
      $q.notify({
        type: 'negative',
        message: `Failed to connect: ${e instanceof Error ? e.message : String(e)}`,
      });
    });
}

function onRemoveDevice(devId: string) {
  $q.dialog({
    title: 'Remove Device',
    message: `Are you sure you want to remove '${devId}' from the configuration?`,
    cancel: true,
    persistent: true,
  }).onOk(() => {
    configStore
      .deleteDevice(devId)
      .then(() => {
        store.selectNode(null);
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
</script>

<style scoped>
.device-page {
  min-height: calc(100vh - 50px);
}

.no-selection {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: calc(100vh - 100px);
  text-align: center;
}
</style>
