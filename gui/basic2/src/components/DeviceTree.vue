<template>
  <div class="device-tree">
    <div class="tree-header q-pa-sm">
      <div class="row items-center justify-between">
        <div class="text-subtitle2 text-grey-8">Devices</div>
        <div>
          <q-btn flat dense size="sm" icon="add" @click="showAddDialog = true">
            <q-tooltip>Add device</q-tooltip>
          </q-btn>
          <q-btn flat dense size="sm" icon="refresh" @click="onRefresh">
            <q-tooltip>Refresh</q-tooltip>
          </q-btn>
          <q-btn flat dense size="sm" icon="unfold_less" @click="collapseAll">
            <q-tooltip>Collapse all</q-tooltip>
          </q-btn>
          <q-btn flat dense size="sm" icon="unfold_more" @click="expandAll">
            <q-tooltip>Expand all</q-tooltip>
          </q-btn>
        </div>
      </div>
      <q-input v-model="filter" dense outlined placeholder="Filter..." class="q-mt-xs">
        <template #prepend>
          <q-icon name="search" size="xs" />
        </template>
        <template #append v-if="filter">
          <q-icon name="close" size="xs" class="cursor-pointer" @click="filter = ''" />
        </template>
      </q-input>
    </div>

    <q-scroll-area class="tree-scroll">
      <q-tree
        ref="treeRef"
        :nodes="allTreeNodes as unknown as object[]"
        node-key="id"
        v-model:selected="selectedNode"
        :filter="filter"
        :filter-method="filterMethod"
        default-expand-all
        dense
        @update:selected="onSelect"
      >
        <template #default-header="prop">
          <div
            class="row items-center tree-node full-width"
            :class="{
              'selected-node': prop.node.id === selectedNode,
              'disconnected-node': prop.node.connected === false,
            }"
          >
            <q-icon
              v-if="prop.node.icon"
              :name="prop.node.icon"
              :color="prop.node.iconColor"
              size="xs"
              class="q-mr-xs"
            />
            <span class="tree-label col">{{ prop.node.label }}</span>
            <!-- Context menu for connected device nodes -->
            <q-menu v-if="prop.node.nodeType === 'device' && prop.node.connected !== false" context-menu>
              <q-list dense style="min-width: 150px">
                <q-item clickable v-close-popup @click="onDisconnect(prop.node.deviceId)">
                  <q-item-section avatar><q-icon name="link_off" size="xs" color="orange" /></q-item-section>
                  <q-item-section>Disconnect</q-item-section>
                </q-item>
              </q-list>
            </q-menu>
            <!-- Context menu for disconnected device nodes -->
            <q-menu v-if="prop.node.nodeType === 'device' && prop.node.connected === false" context-menu>
              <q-list dense style="min-width: 150px">
                <q-item clickable v-close-popup @click="onConnect(prop.node.deviceId)">
                  <q-item-section avatar><q-icon name="link" size="xs" color="positive" /></q-item-section>
                  <q-item-section>Connect</q-item-section>
                </q-item>
                <q-item clickable v-close-popup @click="onRemove(prop.node.deviceId)">
                  <q-item-section avatar><q-icon name="delete" size="xs" color="negative" /></q-item-section>
                  <q-item-section class="text-negative">Remove</q-item-section>
                </q-item>
              </q-list>
            </q-menu>
          </div>
        </template>
      </q-tree>

      <div v-if="store.loading" class="q-pa-sm text-center text-grey">
        <q-spinner size="sm" class="q-mr-xs" />
        Loading...
      </div>

      <div
        v-if="!store.loading && allTreeNodes.length === 0"
        class="q-pa-sm text-center text-grey"
      >
        No devices found
      </div>
    </q-scroll-area>

    <!-- Add device dialog -->
    <q-dialog v-model="showAddDialog">
      <q-card style="min-width: 400px">
        <q-card-section>
          <div class="text-h6">Add New Device</div>
        </q-card-section>
        <q-card-section>
          <q-input
            v-model="newDeviceId"
            dense
            outlined
            label="Device ID"
            hint="Unique identifier for this device"
            :rules="[
              (v: string) => !!v || 'Required',
              (v: string) => !deviceIdExists(v) || 'ID already exists',
            ]"
            class="q-mb-md"
          />
          <div class="row q-col-gutter-md">
            <div class="col-6">
              <q-select
                v-model="newDeviceVendor"
                label="Vendor"
                :options="vendorOptions"
                outlined
                dense
                emit-value
                map-options
                @update:model-value="newDeviceDriver = ''"
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
            unelevated
            color="primary"
            label="Add"
            :disable="!newDeviceId || !newDeviceDriver || deviceIdExists(newDeviceId)"
            :loading="configStore.loading"
            @click="addDevice"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useQuasar } from 'quasar';
import { useDevicesStore, type TreeNode } from 'stores/devices';
import { useMacrosStore } from 'stores/macros';
import { useConfigStore } from 'stores/config';

const $q = useQuasar();
const store = useDevicesStore();
const macrosStore = useMacrosStore();
const configStore = useConfigStore();
const treeRef = ref();
const filter = ref('');

// Add device dialog state
const showAddDialog = ref(false);
const newDeviceId = ref('');
const newDeviceVendor = ref<string | null>(null);
const newDeviceDriver = ref('');

const selectedNode = computed({
  get: () => store.selectedNodeId,
  set: (val) => store.selectNode(val),
});

// Combine connected device tree with disconnected device nodes
const allTreeNodes = computed<TreeNode[]>(() => {
  const connected = store.treeNodes;
  const disconnected: TreeNode[] = configStore.disconnectedDevices.map((d) => ({
    id: d.id,
    label: d.id,
    icon: 'link_off',
    iconColor: 'grey-5',
    nodeType: 'device' as const,
    deviceId: d.id,
    devicePath: d.id,
    connected: false,
  }));
  return [...connected, ...disconnected];
});

// Vendor options for Add Device dialog
const vendorOptions = computed(() => {
  const vendors = new Set(configStore.drivers.map((d) => d.vendor));
  return Array.from(vendors).sort().map((v) => ({ label: v, value: v }));
});

// Device options filtered by selected vendor
const newDeviceOptions = computed(() => {
  if (!newDeviceVendor.value) return [];
  return configStore.drivers
    .filter((d) => d.vendor === newDeviceVendor.value)
    .sort((a, b) => a.name.localeCompare(b.name));
});

function deviceIdExists(id: string): boolean {
  return allTreeNodes.value.some((n) => n.id === id);
}

function filterMethod(node: TreeNode, filter: string): boolean {
  const f = filter.toLowerCase();
  if (node.label.toLowerCase().includes(f)) return true;
  if (node.children) {
    return node.children.some((c) => filterMethod(c, filter));
  }
  return false;
}

function onSelect(nodeId: string | null) {
  if (nodeId) {
    macrosStore.selectNode(null);
  }
  store.selectNode(nodeId);
}

function expandAll() {
  treeRef.value?.expandAll();
}

function collapseAll() {
  treeRef.value?.collapseAll();
}

function onDisconnect(deviceId: string) {
  store.disconnectDevice(deviceId)
    .then(() => {
      $q.notify({ type: 'positive', message: `Device '${deviceId}' disconnected` });
    })
    .catch((e: unknown) => {
      $q.notify({
        type: 'negative',
        message: `Failed to disconnect: ${e instanceof Error ? e.message : String(e)}`,
      });
    });
}

function onConnect(deviceId: string) {
  store.connectDevice(deviceId)
    .then(() => {
      $q.notify({ type: 'positive', message: `Device '${deviceId}' connected` });
    })
    .catch((e: unknown) => {
      $q.notify({
        type: 'negative',
        message: `Failed to connect: ${e instanceof Error ? e.message : String(e)}`,
      });
    });
}

function onRemove(deviceId: string) {
  $q.dialog({
    title: 'Remove Device',
    message: `Are you sure you want to remove '${deviceId}' from the configuration?`,
    cancel: true,
    persistent: true,
  }).onOk(() => {
    configStore.deleteDevice(deviceId)
      .then(() => {
        if (store.selectedNodeId === deviceId) {
          store.selectNode(null);
        }
        $q.notify({ type: 'positive', message: `Device '${deviceId}' removed` });
      })
      .catch((e: unknown) => {
        $q.notify({
          type: 'negative',
          message: `Failed to remove: ${e instanceof Error ? e.message : String(e)}`,
        });
      });
  });
}

async function onRefresh() {
  try {
    await Promise.all([configStore.loadConfig(), store.loadDevices()]);
    $q.notify({ type: 'info', message: 'Refreshed', timeout: 1000 });
  } catch (e: unknown) {
    $q.notify({
      type: 'negative',
      message: `Refresh failed: ${e instanceof Error ? e.message : String(e)}`,
    });
  }
}

async function addDevice() {
  if (!newDeviceId.value || !newDeviceDriver.value) return;
  try {
    await configStore.addDevice(newDeviceId.value, newDeviceDriver.value);
    showAddDialog.value = false;
    // Select the new device
    store.selectNode(newDeviceId.value);
    macrosStore.selectNode(null);
    $q.notify({ type: 'positive', message: `Device '${newDeviceId.value}' added` });
    newDeviceId.value = '';
    newDeviceVendor.value = null;
    newDeviceDriver.value = '';
  } catch (e: unknown) {
    $q.notify({
      type: 'negative',
      message: `Failed to add device: ${e instanceof Error ? e.message : String(e)}`,
    });
  }
}
</script>

<style scoped>
.device-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.tree-header {
  border-bottom: 1px solid rgba(0, 0, 0, 0.1);
}

.tree-scroll {
  flex: 1;
  min-height: 0;
}

.tree-node {
  padding: 1px 4px;
  border-radius: 3px;
  margin: -1px 0;
}

.tree-node.selected-node {
  background-color: #e3f2fd; /* light-blue-2 */
  color: #0d47a1; /* dark blue */
  font-weight: 500;
}

.tree-node.disconnected-node {
  opacity: 0.6;
}

.tree-label {
  font-size: 13px;
}

:deep(.q-tree__node-header) {
  padding: 2px 4px;
}

:deep(.q-tree__node) {
  padding: 0;
}
</style>
