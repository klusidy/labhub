<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated class="bg-green-10">
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
          <span class="text-weight-bold">LabHub | DEVICES</span>
          <span class="q-mx-sm text-grey-4">|</span>
          <span class="config-path">{{ store.configPath || 'Loading...' }}</span>
        </q-toolbar-title>

        <q-space />

        <!-- Global config actions -->
        <q-btn
          flat
          icon="refresh"
          label="Reload All"
          :loading="store.loading"
          @click="softReloadAll"
        >
          <q-tooltip>Apply config changes to all devices</q-tooltip>
        </q-btn>

        <q-btn flat icon="download" label="Download" @click="store.downloadConfigFile()">
          <q-tooltip>Download config.yaml</q-tooltip>
        </q-btn>

        <q-btn flat icon="help_outline" @click="showHelp = true" label="Help">
          <q-tooltip>Help</q-tooltip>
        </q-btn>
      </q-toolbar>
    </q-header>

    <q-page-container>
      <router-view />
    </q-page-container>

    <!-- Help Dialog -->
    <q-dialog v-model="showHelp">
      <q-card style="min-width: 500px; max-width: 700px">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">LabHub Config Manager</div>
          <q-space />
          <q-btn icon="close" flat round dense v-close-popup />
        </q-card-section>

        <q-card-section>
          <div class="text-subtitle2 q-mb-sm">Device Management</div>
          <ul class="q-pl-md q-my-sm">
            <li>
              <strong>Add Device:</strong> Click "Add Device" in the sidebar to create a new device
              entry
            </li>
            <li>
              <strong>Edit Device:</strong> Select a device from the list to edit its configuration
            </li>
            <li>
              <strong>Save:</strong> Saves the device config to the YAML file (does not reload the
              device)
            </li>
            <li><strong>Reload:</strong> Saves config AND restarts the device with new settings</li>
            <li>
              <strong>Delete:</strong> Removes the device from config (requires Reload All to take
              effect)
            </li>
          </ul>

          <q-separator class="q-my-md" />

          <div class="text-subtitle2 q-mb-sm">Configuration Options</div>
          <ul class="q-pl-md q-my-sm">
            <li><strong>Device ID:</strong> Unique identifier used in API calls</li>
            <li><strong>Driver:</strong> Select vendor and device type from available drivers</li>
            <li>
              <strong>Additional Options:</strong> Device-specific settings in YAML format (e.g.,
              serial port, channels)
            </li>
          </ul>

          <q-separator class="q-my-md" />

          <div class="text-subtitle2 q-mb-sm">Status Indicators</div>
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
            <div class="row items-center">
              <q-icon name="help_outline" color="grey" class="q-mr-xs" />
              <span>Unknown</span>
            </div>
          </div>

          <q-separator class="q-my-md" />

          <div class="text-subtitle2 q-mb-sm">Header Actions</div>
          <ul class="q-pl-md q-my-sm">
            <li>
              <strong>Reload All:</strong> Applies config changes - adds new devices, removes
              deleted ones, restarts changed ones
            </li>
            <li><strong>Download:</strong> Downloads the current config.yaml file</li>
          </ul>
        </q-card-section>

        <q-card-actions align="right">
          <q-btn flat label="Close" color="primary" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-layout>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useQuasar } from 'quasar';
import { useConfigStore } from 'stores/config';

const $q = useQuasar();
const store = useConfigStore();
const showHelp = ref(false);

function navigateTo(path: string) {
  // Navigate to different apps (external navigation)
  window.location.href = path;
}

async function softReloadAll() {
  try {
    const result = await store.softReloadAll();
    $q.notify({
      type: 'positive',
      message: `Reload complete: ${result.added.length} added, ${result.removed.length} removed, ${result.restarted.length} restarted`,
    });
  } catch (e) {
    $q.notify({
      type: 'negative',
      message: `Reload failed: ${e instanceof Error ? e.message : String(e)}`,
    });
  }
}
</script>

<style scoped>
.config-path {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 0.85em;
  opacity: 0.9;
}
</style>
