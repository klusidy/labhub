<template>
  <q-page class="q-pa-md">
    <ProfileTree
      :nodes="store.treeNodes"
      :loading="store.loading"
      @policy-change="onPolicyChange"
    />

    <!-- Loading overlay -->
    <q-inner-loading :showing="store.loading && store.devices.length === 0">
      <q-spinner-dots size="50px" color="indigo" />
    </q-inner-loading>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { useQuasar } from 'quasar';
import { useProfileStore } from 'stores/profile';
import ProfileTree from 'components/ProfileTree.vue';

const $q = useQuasar();
const store = useProfileStore();

async function onPolicyChange(deviceId: string, propName: string, policy: 'read' | 'write') {
  try {
    await store.setPropertyPolicy(deviceId, propName, policy);
    $q.notify({
      type: 'positive',
      message: `Policy for ${deviceId}.${propName} set to "${policy}"`,
      position: 'bottom-right',
    });
  } catch (e) {
    $q.notify({
      type: 'negative',
      message: `Failed to set policy: ${e instanceof Error ? e.message : String(e)}`,
    });
  }
}

onMounted(async () => {
  try {
    await store.loadProfile();
  } catch (e) {
    $q.notify({
      type: 'negative',
      message: `Failed to load profile: ${e instanceof Error ? e.message : String(e)}`,
    });
  }
});
</script>
