<template>
  <q-page class="device-page">
    <!-- No selection state -->
    <div v-if="!store.selectedNodeId" class="no-selection">
      <q-icon name="touch_app" size="xl" color="grey-4" />
      <div class="text-h6 text-grey-6 q-mt-md">Select a device</div>
      <div class="text-caption text-grey-5">
        Click on a device or item in the tree to view details
      </div>
    </div>

    <!-- Device selected - show full device view -->
    <div v-else-if="nodeType === 'device' && selectedDevice" class="q-pa-md">
      <div class="row items-center q-mb-md">
        <q-icon
          :name="getStatusIcon(selectedDevice.status)"
          :color="getStatusColor(selectedDevice.status)"
          size="md"
          class="q-mr-sm"
        />
        <div>
          <div class="text-h5">{{ selectedDevice.id }}</div>
          <div class="text-caption text-grey-6">{{ selectedDevice.kind }}</div>
        </div>
      </div>

      <div v-if="selectedDevice.doc" class="q-mb-md text-body2 text-grey-7">
        {{ selectedDevice.doc }}
      </div>

      <!-- All sections for device -->
      <DataSourcePanel v-if="hasDataSources" :device-id="selectedDevice.id" />
      <PropertyTable v-if="hasProperties" :device-id="selectedDevice.id" />
      <CommandPanel v-if="hasCommands" :device-id="selectedDevice.id" />
    </div>

    <!-- Category selected (properties/commands/dataSources) -->
    <div v-else-if="nodeType === 'category' && selectedDevice" class="q-pa-md">
      <div class="row items-center q-mb-md">
        <q-btn flat dense round icon="arrow_back" @click="store.selectNode(selectedDevice.id)" />
        <div class="q-ml-sm">
          <div class="text-h6">{{ categoryTitle }}</div>
          <div class="text-caption text-grey-6">{{ selectedDevice.id }}</div>
        </div>
      </div>

      <DataSourcePanel v-if="categoryType === 'dataSources'" :device-id="selectedDevice.id" />
      <PropertyTable v-if="categoryType === 'properties'" :device-id="selectedDevice.id" />
      <CommandPanel v-if="categoryType === 'commands'" :device-id="selectedDevice.id" />
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
        :device-id="selectedDevice.id"
        :filter-source="itemName"
      />
      <PropertyTable
        v-if="nodeType === 'property'"
        :device-id="selectedDevice.id"
        :filter-prop="itemName"
      />
      <CommandPanel
        v-if="nodeType === 'command'"
        :device-id="selectedDevice.id"
        :filter-cmd="itemName"
      />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useDevicesStore } from 'stores/devices';
import PropertyTable from 'components/PropertyTable.vue';
import CommandPanel from 'components/CommandPanel.vue';
import DataSourcePanel from 'components/DataSourcePanel.vue';

const store = useDevicesStore();

const selectedDevice = computed(() => store.selectedDevice);
const selectedSpec = computed(() => store.selectedSpec);
const nodeType = computed(() => store.selectedNodeType);
const categoryType = computed(() => store.selectedCategoryType);
const itemName = computed(() => store.selectedItemName);

const hasProperties = computed(() => (selectedSpec.value?.properties?.length || 0) > 0);
const hasCommands = computed(() => (selectedSpec.value?.commands?.length || 0) > 0);
const hasDataSources = computed(() => (selectedSpec.value?.data_sources?.length || 0) > 0);

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
  if (!selectedDevice.value || !nodeType.value) return;
  const catMap: Record<string, string> = {
    property: 'properties',
    command: 'commands',
    dataSource: 'dataSources',
  };
  const cat = catMap[nodeType.value];
  if (cat) {
    store.selectNode(`${selectedDevice.value.id}:${cat}`);
  } else {
    store.selectNode(selectedDevice.value.id);
  }
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
