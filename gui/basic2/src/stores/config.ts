import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import * as adminApi from '../api/admin';
import type { DeviceConfig, DriverInfo } from '../api/admin';
import { useDevicesStore } from './devices';

export const useConfigStore = defineStore('config', () => {
  // State
  const configDevices = ref<DeviceConfig[]>([]);
  const drivers = ref<DriverInfo[]>([]);
  const influx = ref<Record<string, unknown> | undefined>(undefined);
  const configPath = ref('');
  const loading = ref(false);

  // Computed: devices in config but NOT currently connected
  const disconnectedDevices = computed(() => {
    const devicesStore = useDevicesStore();
    const connectedIds = new Set(devicesStore.devices.map((d) => d.id));
    return configDevices.value.filter((d) => !connectedIds.has(d.id));
  });

  // Actions
  async function loadConfig() {
    loading.value = true;
    try {
      const resp = await adminApi.getConfig();
      configPath.value = resp.path;
      configDevices.value = resp.config.devices || [];
      influx.value = resp.config.influx;
    } catch (e) {
      console.error('Failed to load config:', e);
    } finally {
      loading.value = false;
    }
  }

  async function loadDrivers() {
    try {
      const resp = await adminApi.listDrivers();
      drivers.value = resp.drivers;
    } catch (e) {
      console.error('Failed to load drivers:', e);
    }
  }

  function getConfigDevice(devId: string): DeviceConfig | null {
    return configDevices.value.find((d) => d.id === devId) || null;
  }

  function updateDeviceLocally(devId: string, config: DeviceConfig) {
    const idx = configDevices.value.findIndex((d) => d.id === devId);
    if (idx >= 0) {
      configDevices.value[idx] = config;
    }
  }

  async function saveDevice(devId: string) {
    const device = configDevices.value.find((d) => d.id === devId);
    if (!device) throw new Error(`Device ${devId} not found in config`);

    loading.value = true;
    try {
      await adminApi.updateDeviceConfig(devId, device);
    } finally {
      loading.value = false;
    }
  }

  async function deleteDevice(devId: string) {
    loading.value = true;
    try {
      await adminApi.deleteDeviceConfig(devId);
      configDevices.value = configDevices.value.filter((d) => d.id !== devId);
    } finally {
      loading.value = false;
    }
  }

  async function addDevice(id: string, driver: string) {
    const newDevice: DeviceConfig = { id, driver };
    loading.value = true;
    try {
      await adminApi.updateDeviceConfig(id, newDevice);
      configDevices.value.push(newDevice);
    } finally {
      loading.value = false;
    }
  }

  function updateAdditionalConfig(config: Record<string, unknown> | undefined) {
    influx.value = config;
  }

  async function saveAdditionalConfig() {
    loading.value = true;
    try {
      await adminApi.updateConfig(configDevices.value, influx.value);
    } finally {
      loading.value = false;
    }
  }

  return {
    // State
    configDevices,
    drivers,
    influx,
    configPath,
    loading,

    // Computed
    disconnectedDevices,

    // Actions
    loadConfig,
    loadDrivers,
    getConfigDevice,
    updateDeviceLocally,
    saveDevice,
    deleteDevice,
    addDevice,
    updateAdditionalConfig,
    saveAdditionalConfig,
  };
});
