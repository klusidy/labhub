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

        <!-- REPL Terminal Toggle -->
        <q-btn flat icon="terminal" label="Python" @click="replOpen = !replOpen">
          <q-tooltip>{{ replOpen ? 'Hide' : 'Show' }} Python REPL</q-tooltip>
        </q-btn>

        <!-- Server Settings button -->
        <q-btn flat icon="settings" @click="showSettings = true">
          <q-tooltip>Server Settings</q-tooltip>
        </q-btn>

        <!-- Help button -->
        <q-btn flat icon="help_outline" @click="showHelp = true">
          <q-tooltip>Help</q-tooltip>
        </q-btn>
      </q-toolbar>
    </q-header>

    <!-- Left Drawer - Device Tree & Macro Tree -->
    <q-drawer v-model="leftDrawerOpen" show-if-above bordered :width="240" :breakpoint="960">
      <div class="drawer-content">
        <div class="drawer-section">
          <DeviceTree />
        </div>
        <div class="drawer-section">
          <MacroTree />
        </div>
      </div>
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
      <div class="main-content-wrapper">
        <div class="page-content" :class="{ 'with-repl': replOpen }">
          <router-view />
        </div>
        <div v-if="replOpen" class="repl-container">
          <ReplTerminal @close="replOpen = false" />
        </div>
      </div>
    </q-page-container>

    <!-- Floating button to reopen console -->

    <q-page-sticky position="bottom-right" :offset="[64, 8]">
      <q-btn
        v-if="!replOpen"
        fab-mini
        icon="terminal"
        color="blue-grey-8"
        class="repl-fab"
        @click="replOpen = true"
      >
        <q-tooltip>Open Python REPL</q-tooltip>
      </q-btn>
    </q-page-sticky>

    <!-- Settings Dialog -->
    <q-dialog v-model="showSettings">
      <q-card style="min-width: 500px; max-width: 700px">
        <q-card-section class="row items-center q-pb-none">
          <div>
            <div class="text-h6">Server Settings</div>
            <div v-if="configStore.configPath" class="text-caption text-grey-6">
              {{ configStore.configPath }}
            </div>
          </div>
          <q-space />
          <q-btn icon="close" flat round dense v-close-popup />
        </q-card-section>

        <q-card-section>
          <div class="text-subtitle2 q-mb-xs">Additional Config (YAML)</div>
          <div class="text-caption text-grey-7 q-mb-sm">
            Extra configuration (e.g., InfluxDB settings)
          </div>
          <q-input
            v-model="settingsYaml"
            type="textarea"
            outlined
            dense
            :rows="12"
            class="settings-textarea"
            placeholder="# Example:
influx:
  enabled: true
  url: http://localhost:8086
  token: your-token
  org: your-org
  bucket: labhub"
            :error="!!settingsYamlError"
            :error-message="settingsYamlError ?? undefined"
            @update:model-value="onSettingsYamlChange"
          />
        </q-card-section>

        <q-card-actions align="right">
          <q-btn flat label="Cancel" v-close-popup />
          <q-btn
            unelevated
            color="primary"
            label="Save"
            icon="save"
            :disable="!!settingsYamlError"
            :loading="configStore.loading"
            @click="saveSettings"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

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
import { ref, watch, onMounted, onUnmounted } from 'vue';
import { useQuasar } from 'quasar';
import yaml from 'js-yaml';
import { useDevicesStore } from 'stores/devices';
import { useMacrosStore } from 'stores/macros';
import { useConfigStore } from 'stores/config';
import DeviceTree from 'components/DeviceTree.vue';
import MacroTree from 'components/MacroTree.vue';
import WorkspacePanel from 'components/WorkspacePanel.vue';
import ReplTerminal from 'components/ReplTerminal.vue';

const $q = useQuasar();
const store = useDevicesStore();
const macrosStore = useMacrosStore();
const configStore = useConfigStore();

const leftDrawerOpen = ref(false);
const rightDrawerOpen = ref(false);
const showHelp = ref(false);
const showSettings = ref(false);
const settingsYaml = ref('');
const settingsYamlError = ref<string | null>(null);
const replOpen = ref(localStorage.getItem('labhub_repl_open') === 'true');

watch(replOpen, (val) => {
  localStorage.setItem('labhub_repl_open', val ? 'true' : 'false');
});

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

function influxToYaml(influx: Record<string, unknown> | undefined): string {
  if (!influx || Object.keys(influx).length === 0) return '';
  try {
    return yaml.dump({ influx }, { indent: 2, lineWidth: -1 });
  } catch {
    return '';
  }
}

function yamlToInflux(yamlStr: string): Record<string, unknown> | undefined {
  if (!yamlStr.trim()) return undefined;
  const parsed = yaml.load(yamlStr) as Record<string, unknown> | null;
  if (!parsed) return undefined;
  if ('influx' in parsed) {
    return parsed.influx as Record<string, unknown>;
  }
  return parsed;
}

function onSettingsYamlChange() {
  try {
    yamlToInflux(settingsYaml.value);
    settingsYamlError.value = null;
  } catch (e) {
    settingsYamlError.value = e instanceof Error ? e.message : 'Invalid YAML';
  }
}

async function saveSettings() {
  try {
    const parsed = yamlToInflux(settingsYaml.value);
    configStore.updateAdditionalConfig(parsed);
    await configStore.saveAdditionalConfig();
    showSettings.value = false;
    $q.notify({ type: 'positive', message: 'Settings saved' });
  } catch (e: unknown) {
    $q.notify({
      type: 'negative',
      message: `Failed to save: ${e instanceof Error ? e.message : String(e)}`,
    });
  }
}

watch(showSettings, (val) => {
  if (val) {
    settingsYaml.value = influxToYaml(configStore.influx);
    settingsYamlError.value = null;
  }
});

onMounted(async () => {
  await Promise.all([
    store.loadDevices(),
    configStore.loadConfig(),
    configStore.loadDrivers(),
    macrosStore.loadMacros(),
  ]);
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

.main-content-wrapper {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 50px);
}

.page-content {
  flex: 1;
  overflow: auto;
}

.page-content.with-repl {
  flex: 1;
  max-height: 60vh;
}

.repl-container {
  height: calc(40vh - 40px);
  border-top: 2px solid rgba(0, 0, 0, 0.12);
}

.repl-fab {
  position: fixed;
  bottom: 16px;
  left: 16px;
  z-index: 100;
}

.drawer-content {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.drawer-section {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.settings-textarea :deep(textarea) {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}
</style>
