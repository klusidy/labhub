<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated class="bg-indigo-9">
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
          <span class="text-weight-bold">LabHub | PROFILE</span>
          <span class="q-mx-sm text-indigo-3">|</span>
          <span class="profile-path">{{ store.profilePath || 'Loading...' }}</span>
        </q-toolbar-title>

        <q-space />

        <!-- Download button -->
        <q-btn flat icon="download" label="Download" @click="store.downloadProfileFile()">
          <q-tooltip>Download profile.yaml</q-tooltip>
        </q-btn>

        <!-- Help button -->
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
          <div class="text-h6">LabHub Profile Manager</div>
          <q-space />
          <q-btn icon="close" flat round dense v-close-popup />
        </q-card-section>

        <q-card-section>
          <div class="text-subtitle2 q-mb-sm">What is a Profile?</div>
          <p class="q-my-sm">
            A profile stores device property values and their restore policies. When a profile is
            loaded, properties with "write" policy are restored to their saved values.
          </p>

          <q-separator class="q-my-md" />

          <div class="text-subtitle2 q-mb-sm">Property Policies</div>
          <div class="row q-gutter-md q-my-sm">
            <div class="row items-center">
              <q-icon name="edit" color="indigo-7" class="q-mr-xs" />
              <strong>Write:</strong>
              <span class="q-ml-xs">Value is restored when profile loads</span>
            </div>
          </div>
          <div class="row q-gutter-md q-my-sm">
            <div class="row items-center">
              <q-icon name="visibility" color="grey-7" class="q-mr-xs" />
              <strong>Read:</strong>
              <span class="q-ml-xs">Value is monitored but not restored</span>
            </div>
          </div>
          <div class="row q-gutter-md q-my-sm">
            <div class="row items-center">
              <q-icon name="lock" color="grey-6" class="q-mr-xs" />
              <strong>Read-only:</strong>
              <span class="q-ml-xs">Property cannot have write policy</span>
            </div>
          </div>

          <q-separator class="q-my-md" />

          <div class="text-subtitle2 q-mb-sm">How It Works</div>
          <ul class="q-pl-md q-my-sm">
            <li>
              <strong>Automatic Saves:</strong> Profile is saved every 10 seconds with current
              device states
            </li>
            <li>
              <strong>Policy Changes:</strong> Clicking the toggle immediately changes the policy
              and saves
            </li>
            <li>
              <strong>Profile Load:</strong> On startup, write-policy properties are restored to
              devices
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
import { ref } from 'vue';
import { useProfileStore } from 'stores/profile';

const store = useProfileStore();
const showHelp = ref(false);

function navigateTo(path: string) {
  // Navigate to different apps (external navigation)
  window.location.href = path;
}
</script>

<style scoped>
.profile-path {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 0.85em;
  opacity: 0.9;
}
</style>
