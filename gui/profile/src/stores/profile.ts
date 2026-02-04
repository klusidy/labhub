import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import * as api from '../api/profile';
import type { DeviceSpec } from '../api/profile';

export interface PropertyData {
  value: unknown;
  policy: 'read' | 'write';
  readOnly: boolean;
}

export interface DeviceData {
  id: string;
  driver: string;
  status: 'connected' | 'disconnected' | 'unhealthy';
  properties: Record<string, PropertyData>;
}

export const useProfileStore = defineStore('profile', () => {
  // State
  const profilePath = ref<string | null>(null);
  const rawProfile = ref<string>('');
  const devices = ref<DeviceData[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  // Computed - tree nodes for q-tree
  const treeNodes = computed(() => {
    return devices.value.map((dev) => ({
      label: dev.id,
      id: dev.id,
      icon: getDeviceIcon(dev.status),
      iconColor: getDeviceColor(dev.status),
      driver: dev.driver,
      status: dev.status,
      selectable: false,
      children: Object.entries(dev.properties).map(([propName, propData]) => ({
        label: propName,
        id: `${dev.id}.${propName}`,
        deviceId: dev.id,
        propName,
        value: propData.value,
        policy: propData.policy,
        readOnly: propData.readOnly,
        selectable: false,
      })),
    }));
  });

  // Helper functions
  function getDeviceIcon(status: string): string {
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

  function getDeviceColor(status: string): string {
    switch (status) {
      case 'connected':
        return 'indigo-9';
      case 'disconnected':
        return 'negative';
      case 'unhealthy':
        return 'warning';
      default:
        return 'grey';
    }
  }

  // Actions
  async function loadProfile() {
    loading.value = true;
    error.value = null;
    try {
      // Get profile info (path, raw, policies)
      const profile = await api.getProfile();
      profilePath.value = profile.path;
      rawProfile.value = profile.raw;

      // Get device states
      const deviceStates = await api.listDevices();

      // Get device specs for read_only info and merge with state
      const deviceDataList: DeviceData[] = [];

      for (const devState of deviceStates) {
        let spec: DeviceSpec | null = null;
        try {
          spec = await api.getDeviceSpec(devState.id);
        } catch {
          // Spec unavailable, continue without it
        }

        const properties: Record<string, PropertyData> = {};
        const devicePolicies = profile.policies[devState.id] || {};

        for (const [propName, value] of Object.entries(devState.state)) {
          const policy = (devicePolicies[propName] as 'read' | 'write') || 'write';
          const readOnly = spec?.properties?.[propName]?.read_only ?? false;

          properties[propName] = {
            value,
            policy,
            readOnly,
          };
        }

        deviceDataList.push({
          id: devState.id,
          driver: devState.driver,
          status: devState.status,
          properties,
        });
      }

      devices.value = deviceDataList;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function setPropertyPolicy(
    devId: string,
    propName: string,
    policy: 'read' | 'write'
  ) {
    loading.value = true;
    try {
      await api.setPropertyPolicy(devId, propName, policy);

      // Update local state
      const device = devices.value.find((d) => d.id === devId);
      if (device && device.properties[propName]) {
        device.properties[propName].policy = policy;
      }

      // Refresh raw profile
      const profile = await api.getProfile();
      rawProfile.value = profile.raw;
    } finally {
      loading.value = false;
    }
  }

  function downloadProfileFile() {
    api.downloadProfile(rawProfile.value);
  }

  return {
    // State
    profilePath,
    rawProfile,
    devices,
    loading,
    error,

    // Computed
    treeNodes,

    // Actions
    loadProfile,
    setPropertyPolicy,
    downloadProfileFile,
  };
});
