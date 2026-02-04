<template>
  <q-layout view="hHh LpR fFf">
    <!-- Header -->
    <q-header elevated class="bg-light-blue-10">
      <q-toolbar>
        <!-- Navigation menu -->
        <q-btn flat dense round icon="menu" aria-label="Menu">
          <q-menu>
            <q-list style="min-width: 150px">
              <q-item clickable v-close-popup @click="navigateTo('/ui')">
                <q-item-section avatar>
                  <q-icon name="dashboard" />
                </q-item-section>
                <q-item-section>GUIv2</q-item-section>
              </q-item>
              <q-item clickable v-close-popup @click="navigateTo('/devices')">
                <q-item-section avatar>
                  <q-icon name="settings" />
                </q-item-section>
                <q-item-section>Devices</q-item-section>
              </q-item>
              <q-item clickable v-close-popup @click="navigateTo('/profile')">
                <q-item-section avatar>
                  <q-icon name="account_circle" />
                </q-item-section>
                <q-item-section>Profile</q-item-section>
              </q-item>
              <q-separator />
              <q-item clickable v-close-popup @click="navigateTo('/docs')">
                <q-item-section avatar>
                  <q-icon name="description" />
                </q-item-section>
                <q-item-section>API Docs</q-item-section>
              </q-item>
              <q-item clickable v-close-popup @click="navigateTo('/v1ui')">
                <q-item-section avatar>
                  <q-icon name="dashboard" />
                </q-item-section>
                <q-item-section>GUIv1</q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-btn>

        <q-toolbar-title class="text-subtitle1">
          <span class="text-weight-bold">LabHub | GUIv2</span>
        </q-toolbar-title>

        <q-space />

        <!-- Mobile toggles -->
        <q-btn
          flat
          dense
          round
          icon="account_tree"
          class="lt-md"
          @click="leftDrawerOpen = !leftDrawerOpen"
        >
          <q-tooltip>Device Tree</q-tooltip>
        </q-btn>

        <q-btn
          flat
          dense
          round
          icon="workspaces"
          class="lt-md"
          @click="rightDrawerOpen = !rightDrawerOpen"
        >
          <q-tooltip>Workspace</q-tooltip>
        </q-btn>

        <!-- Snapshot button -->
        <q-btn flat icon="photo_camera" label="Snapshot" @click="onSnapshot">
          <q-tooltip>Download device states as JSON</q-tooltip>
        </q-btn>

        <!-- Help button -->
        <q-btn flat icon="help_outline" @click="showHelp = true">
          <q-tooltip>Help</q-tooltip>
        </q-btn>
      </q-toolbar>
    </q-header>

    <!-- Left Drawer - Device Tree -->
    <q-drawer v-model="leftDrawerOpen" show-if-above bordered :width="240" :breakpoint="960">
      <DeviceTree />
    </q-drawer>

    <!-- Right Drawer - Workspace -->
    <q-drawer
      v-model="rightDrawerOpen"
      side="right"
      show-if-above
      bordered
      :width="420"
      :breakpoint="960"
    >
      <WorkspacePanel />
    </q-drawer>

    <!-- Main content -->
    <q-page-container>
      <router-view />
    </q-page-container>

    <!-- Help Dialog -->
    <q-dialog v-model="showHelp">
      <q-card style="min-width: 500px; max-width: 700px">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">LabHub Device Explorer</div>
          <q-space />
          <q-btn icon="close" flat round dense v-close-popup />
        </q-card-section>

        <q-card-section>
          <div class="text-subtitle2 q-mb-sm">Navigation</div>
          <p class="q-my-sm">
            Use the tree on the left to browse devices. Click on a device to see all its properties,
            commands, and data sources. Click on a category or individual item to focus on specific
            elements.
          </p>

          <q-separator class="q-my-md" />

          <div class="text-subtitle2 q-mb-sm">Workspace</div>
          <p class="q-my-sm">
            Drag properties and commands to the shelf panel on the right to create a custom working
            area. Items in the shelf persist across page reloads and update in real-time.
          </p>

          <q-separator class="q-my-md" />

          <div class="text-subtitle2 q-mb-sm">Properties</div>
          <ul class="q-pl-md q-my-sm">
            <li>View current values and edit writable properties</li>
            <li>
              <q-icon name="lock" size="xs" class="q-mr-xs" />Read-only properties cannot be
              modified
            </li>
          </ul>

          <div class="text-subtitle2 q-mb-sm">Commands</div>
          <ul class="q-pl-md q-my-sm">
            <li>Expand commands to see and edit arguments</li>
            <li>Results are displayed after execution</li>
          </ul>

          <div class="text-subtitle2 q-mb-sm">Data Sources</div>
          <ul class="q-pl-md q-my-sm">
            <li><strong>Once:</strong> Fetch a single frame of data</li>
            <li><strong>Start/Stop:</strong> Stream data continuously</li>
            <li>Adjust the rate (Hz) to control update frequency</li>
            <li>Toggle between linear and log scales</li>
          </ul>

          <q-separator class="q-my-md" />

          <div class="text-subtitle2 q-mb-sm">Status Icons</div>
          <div class="row q-gutter-md q-my-sm">
            <div class="row items-center">
              <q-icon name="check_circle" color="positive" class="q-mr-xs" />
              <span>Connected</span>
            </div>
            <div class="row items-center">
              <q-icon name="cancel" color="negative" class="q-mr-xs" />
              <span>Disconnected</span>
            </div>
            <div class="row items-center">
              <q-icon name="warning" color="warning" class="q-mr-xs" />
              <span>Unhealthy</span>
            </div>
          </div>
        </q-card-section>

        <q-card-actions align="right">
          <q-btn flat label="Close" color="primary" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-layout>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { useDevicesStore } from 'stores/devices';
import DeviceTree from 'components/DeviceTree.vue';
import WorkspacePanel from 'components/WorkspacePanel.vue';

const store = useDevicesStore();

const leftDrawerOpen = ref(false);
const rightDrawerOpen = ref(false);
const showHelp = ref(false);

function navigateTo(path: string) {
  window.location.href = path;
}

function formatNowInTemplate(template: string, now: Date): string {
  const pad2 = (n: number) => String(n).padStart(2, '0');
  const yy = pad2(now.getFullYear() % 100);
  const MM = pad2(now.getMonth() + 1);
  const dd = pad2(now.getDate());
  const HH = pad2(now.getHours());
  const mm = pad2(now.getMinutes());
  const ss = pad2(now.getSeconds());
  const formatted = `${yy}${MM}${dd}_${HH}${mm}${ss}`;
  return template.replace(/{now:%y%m%d_%H%M%S}/g, formatted);
}

function onSnapshot() {
  try {
    const devices = store.devices;
    const now = new Date();
    const baseName = formatNowInTemplate('snapshot_{now:%y%m%d_%H%M%S}', now);
    const filename = `${baseName}.json`;

    const blob = new Blob([JSON.stringify(devices, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error('Snapshot failed', err);
  }
}

onMounted(async () => {
  await store.loadDevices();
  store.startEventsListener();
});

onUnmounted(() => {
  store.stopEventsListener();
});
</script>

<style scoped>
.lt-md {
  display: none;
}

@media (max-width: 959px) {
  .lt-md {
    display: inline-flex;
  }
}
</style>
