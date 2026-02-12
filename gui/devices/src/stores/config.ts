import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import * as api from '../api/admin';
import type {
  DeviceConfig,
  DriverInfo,
  DeviceState,
} from '../api/admin';

export const useConfigStore = defineStore('config', () => {
  // State
  const configPath = ref<string>('');
  const devices = ref<DeviceConfig[]>([]);
  const influx = ref<Record<string, unknown> | undefined>(undefined);
  const rawConfig = ref<string>('');
  const drivers = ref<DriverInfo[]>([]);
  const deviceStates = ref<Map<string, DeviceState>>(new Map());
  const selectedDeviceId = ref<string | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  // Track unsaved changes per device
  const unsavedChanges = ref<Set<string>>(new Set());

  // Track unsaved changes for additional config
  const additionalConfigChanged = ref(false);

  // Computed
  const selectedDevice = computed(() => {
    if (!selectedDeviceId.value) return null;
    return devices.value.find((d) => d.id === selectedDeviceId.value) || null;
  });

  const selectedDeviceState = computed(() => {
    if (!selectedDeviceId.value) return null;
    return deviceStates.value.get(selectedDeviceId.value) || null;
  });

  const driversGroupedByVendor = computed(() => {
    const grouped: Record<string, DriverInfo[]> = {};
    for (const d of drivers.value) {
      const vendor = d.vendor;
      let arr = grouped[vendor];
      if (!arr) {
        arr = [];
        grouped[vendor] = arr;
      }
      arr.push(d);
    }
    return grouped;
  });

  // Actions
  async function loadConfig() {
    loading.value = true;
    error.value = null;
    try {
      const resp = await api.getConfig();
      configPath.value = resp.path;
      devices.value = resp.config.devices || [];
      influx.value = resp.config.influx;
      rawConfig.value = resp.raw;
      unsavedChanges.value.clear();
      additionalConfigChanged.value = false;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function loadDrivers() {
    try {
      const resp = await api.listDrivers();
      drivers.value = resp.drivers;
    } catch (e) {
      console.error('Failed to load drivers:', e);
    }
  }

  async function loadDeviceStates() {
    try {
      const states = await api.listDevices();
      deviceStates.value = new Map(states.map((s) => [s.id, s]));
    } catch (e) {
      console.error('Failed to load device states:', e);
    }
  }

  function selectDevice(devId: string | null) {
    selectedDeviceId.value = devId;
  }

  function updateDeviceLocally(originalId: string, config: DeviceConfig) {
    const idx = devices.value.findIndex((d) => d.id === originalId);
    const existingDevice = devices.value[idx];
    if (idx >= 0 && existingDevice) {
      const oldId = existingDevice.id;
      devices.value[idx] = config;

      // If ID changed, update tracking
      if (config.id !== oldId) {
        // Update selectedDeviceId if this is the selected device
        if (selectedDeviceId.value === oldId) {
          selectedDeviceId.value = config.id;
        }
        // Update unsaved changes tracking
        unsavedChanges.value.delete(oldId);
      }
    }
    unsavedChanges.value.add(config.id);
  }

  async function saveDevice(devId: string) {
    const device = devices.value.find((d) => d.id === devId);
    if (!device) throw new Error(`Device ${devId} not found`);

    loading.value = true;
    try {
      await api.updateDeviceConfig(devId, device);
      unsavedChanges.value.delete(devId);
    } finally {
      loading.value = false;
    }
  }

  async function deleteDevice(devId: string) {
    loading.value = true;
    try {
      await api.deleteDeviceConfig(devId);
      devices.value = devices.value.filter((d) => d.id !== devId);
      unsavedChanges.value.delete(devId);
      if (selectedDeviceId.value === devId) {
        selectedDeviceId.value = devices.value[0]?.id || null;
      }
    } finally {
      loading.value = false;
    }
  }

  function addDevice(id: string, driver: string) {
    const newDevice: DeviceConfig = { id, driver };
    devices.value.push(newDevice);
    unsavedChanges.value.add(id);
    selectedDeviceId.value = id;
  }

  async function reloadDevice(devId: string) {
    loading.value = true;
    try {
      await api.reloadDevice(devId);
      await loadDeviceStates();
    } finally {
      loading.value = false;
    }
  }

  async function connectDevice(devId: string) {
    loading.value = true;
    try {
      await api.connectDevice(devId);
      // Update local should_connect
      const device = devices.value.find((d) => d.id === devId);
      if (device) device.should_connect = true;
      await loadDeviceStates();
    } finally {
      loading.value = false;
    }
  }

  async function disconnectDevice(devId: string) {
    loading.value = true;
    try {
      await api.disconnectDevice(devId);
      // Update local should_connect
      const device = devices.value.find((d) => d.id === devId);
      if (device) device.should_connect = false;
      await loadDeviceStates();
    } finally {
      loading.value = false;
    }
  }

  function isDeviceConnected(devId: string): boolean {
    const state = deviceStates.value.get(devId);
    return state?.status === 'connected' || state?.status === 'unhealthy';
  }

  async function softReloadAll() {
    loading.value = true;
    try {
      const result = await api.softReload();
      await loadDeviceStates();
      return result;
    } finally {
      loading.value = false;
    }
  }

  async function saveAllDevices() {
    loading.value = true;
    try {
      await api.updateConfig(devices.value, influx.value);
      unsavedChanges.value.clear();
    } finally {
      loading.value = false;
    }
  }

  function downloadConfigFile() {
    api.downloadConfig(rawConfig.value);
  }

  function hasUnsavedChanges(devId: string): boolean {
    return unsavedChanges.value.has(devId);
  }

  function getDeviceStatus(devId: string): string {
    return deviceStates.value.get(devId)?.status || 'unknown';
  }

  function updateAdditionalConfig(config: Record<string, unknown> | undefined) {
    influx.value = config;
    additionalConfigChanged.value = true;
  }

  async function saveAdditionalConfig() {
    loading.value = true;
    try {
      await api.updateConfig(devices.value, influx.value);
      additionalConfigChanged.value = false;
    } finally {
      loading.value = false;
    }
  }

  return {
    // State
    configPath,
    devices,
    influx,
    rawConfig,
    drivers,
    deviceStates,
    selectedDeviceId,
    loading,
    error,
    unsavedChanges,
    additionalConfigChanged,

    // Computed
    selectedDevice,
    selectedDeviceState,
    driversGroupedByVendor,

    // Actions
    loadConfig,
    loadDrivers,
    loadDeviceStates,
    selectDevice,
    updateDeviceLocally,
    saveDevice,
    deleteDevice,
    addDevice,
    reloadDevice,
    connectDevice,
    disconnectDevice,
    isDeviceConnected,
    softReloadAll,
    saveAllDevices,
    downloadConfigFile,
    hasUnsavedChanges,
    getDeviceStatus,
    updateAdditionalConfig,
    saveAdditionalConfig,
  };
});
