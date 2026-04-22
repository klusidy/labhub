import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import * as api from '../api/devices';
import type {
  DeviceState,
  DeviceSpec,
  PropertySpec,
  CommandSpec,
  DataSourceSpec,
} from '../api/devices';

export interface DeviceWithSpec {
  device: DeviceState;
  spec: DeviceSpec | null;
}

export interface TreeNode {
  id: string;
  label: string;
  icon?: string | undefined;
  iconColor?: string | undefined;
  selectable?: boolean | undefined;
  children?: TreeNode[] | undefined;
  // Metadata for selection handling
  nodeType: 'device' | 'childDevice' | 'category' | 'property' | 'command' | 'dataSource';
  deviceId: string; // root device ID (for connect/disconnect)
  devicePath: string; // full path, e.g. 'multi_device/channel_a'
  itemName?: string | undefined;
  connected?: boolean | undefined;
}

export const useDevicesStore = defineStore('devices', () => {
  // State
  const devices = ref<DeviceState[]>([]);
  const specs = ref<Map<string, DeviceSpec | null>>(new Map());
  const loading = ref(false);
  const error = ref<string | null>(null);
  const selectedNodeId = ref<string | null>(null);
  const eventsWs = ref<WebSocket | null>(null);

  // Computed
  const deviceList = computed(() => devices.value);

  const deviceMap = computed(() => {
    const map = new Map<string, DeviceState>();
    for (const d of devices.value) {
      map.set(d.id, d);
    }
    return map;
  });

  // --- Path-aware helpers ---

  function getSpecForPath(path: string): DeviceSpec | null {
    const parts = path.split('/');
    let spec: DeviceSpec | null | undefined = specs.value.get(parts[0] ?? '');
    if (!spec) return null;
    for (const part of parts.slice(1)) {
      spec = spec.children?.[part] ?? null;
      if (!spec) return null;
    }
    return spec;
  }

  function getStateForPath(path: string): Record<string, unknown> {
    const parts = path.split('/');
    const root = devices.value.find((d) => d.id === parts[0]);
    if (!root) return {};
    let state: Record<string, unknown> = root.state;
    for (const part of parts.slice(1)) {
      const child = state[part];
      if (child && typeof child === 'object' && !Array.isArray(child)) {
        state = child as Record<string, unknown>;
      } else {
        return {};
      }
    }
    return state;
  }

  // --- Tree building ---

  function buildDeviceSubtree(devicePath: string, rootId: string, spec: DeviceSpec): TreeNode[] {
    const nodes: TreeNode[] = [];

    // Child devices first (recursively)
    if (spec.children) {
      for (const [childId, childSpec] of Object.entries(spec.children)) {
        const childPath = `${devicePath}/${childId}`;
        const grandchildren = buildDeviceSubtree(childPath, rootId, childSpec);
        nodes.push({
          id: childPath,
          label: childId,
          icon: 'device_hub',
          iconColor: 'blue-grey',
          nodeType: 'childDevice',
          deviceId: rootId,
          devicePath: childPath,
          children: grandchildren.length > 0 ? grandchildren : undefined,
        });
      }
    }

    // Data sources
    if (spec.data_sources?.length) {
      nodes.push({
        id: `${devicePath}:dataSources`,
        label: 'Data Sources',
        icon: 'show_chart',
        nodeType: 'category',
        deviceId: rootId,
        devicePath,
        children: spec.data_sources.map((ds) => ({
          id: `${devicePath}:dataSource:${ds.name}`,
          label: ds.name,
          icon: 'timeline',
          iconColor: 'teal',
          nodeType: 'dataSource' as const,
          deviceId: rootId,
          devicePath,
          itemName: ds.name,
        })),
      });
    }

    // Properties
    if (spec.properties?.length) {
      nodes.push({
        id: `${devicePath}:properties`,
        label: 'Properties',
        icon: 'tune',
        nodeType: 'category',
        deviceId: rootId,
        devicePath,
        children: spec.properties.map((p) => ({
          id: `${devicePath}:property:${p.name}`,
          label: p.name,
          icon: p.read_only ? 'lock' : 'edit',
          iconColor: p.read_only ? 'grey-6' : 'primary',
          nodeType: 'property' as const,
          deviceId: rootId,
          devicePath,
          itemName: p.name,
        })),
      });
    }

    // Commands
    if (spec.commands?.length) {
      nodes.push({
        id: `${devicePath}:commands`,
        label: 'Commands',
        icon: 'play_arrow',
        nodeType: 'category',
        deviceId: rootId,
        devicePath,
        children: spec.commands.map((c) => ({
          id: `${devicePath}:command:${c.name}`,
          label: c.name,
          icon: 'bolt',
          iconColor: 'orange',
          nodeType: 'command' as const,
          deviceId: rootId,
          devicePath,
          itemName: c.name,
        })),
      });
    }

    return nodes;
  }

  const treeNodes = computed<TreeNode[]>(() => {
    return devices.value.map((device) => {
      const spec = specs.value.get(device.id);
      const children = spec ? buildDeviceSubtree(device.id, device.id, spec) : [];
      return {
        id: device.id,
        label: device.id,
        icon: getStatusIcon(device.status),
        iconColor: getStatusColor(device.status),
        nodeType: 'device' as const,
        deviceId: device.id,
        devicePath: device.id,
        connected: device.status === 'connected',
        children: children.length > 0 ? children : undefined,
      };
    });
  });

  // Selection computed
  // The device path is everything before the first ':' in the node ID
  // e.g. 'multi_device/channel_a:property:amplitude' → 'multi_device/channel_a'
  const selectedDevicePath = computed(() => {
    if (!selectedNodeId.value) return null;
    return selectedNodeId.value.split(':')[0] || null;
  });

  // Root device (for status display, connect/disconnect)
  const selectedDevice = computed(() => {
    const path = selectedDevicePath.value;
    if (!path) return null;
    const rootId = path.split('/')[0];
    return devices.value.find((d) => d.id === rootId) || null;
  });

  const selectedSpec = computed(() => {
    const path = selectedDevicePath.value;
    if (!path) return null;
    return getSpecForPath(path);
  });

  const selectedNodeType = computed(() => {
    if (!selectedNodeId.value) return null;
    const parts = selectedNodeId.value.split(':');
    if (parts.length === 1) {
      // bare path — root device or child device
      return (parts[0] ?? '').includes('/') ? 'childDevice' : 'device';
    }
    if (parts.length === 2) return 'category';
    return parts[1] as 'property' | 'command' | 'dataSource';
  });

  const selectedItemName = computed(() => {
    if (!selectedNodeId.value) return null;
    const parts = selectedNodeId.value.split(':');
    return parts.length === 3 ? parts[2] : null;
  });

  const selectedCategoryType = computed(() => {
    if (!selectedNodeId.value) return null;
    const parts = selectedNodeId.value.split(':');
    if (parts.length !== 2) return null;
    const cat = parts[1];
    if (cat === 'properties') return 'properties';
    if (cat === 'commands') return 'commands';
    if (cat === 'dataSources') return 'dataSources';
    return null;
  });

  // Helper functions
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

  // Actions
  async function loadDevices() {
    loading.value = true;
    error.value = null;
    try {
      devices.value = await api.listDevices();

      // Load specs for all devices
      for (const device of devices.value) {
        try {
          const spec = await api.getDeviceSpec(device.id);
          specs.value.set(device.id, spec);
        } catch {
          specs.value.set(device.id, null);
        }
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function updateProperty(deviceId: string, propName: string, value: unknown) {
    await api.patchProperties(deviceId, { [propName]: value });
    // State will be updated via WebSocket
  }

  async function runCommand(
    deviceId: string,
    cmdName: string,
    args: Record<string, unknown> = {},
  ): Promise<unknown> {
    return api.runCommand(deviceId, cmdName, args);
  }

  async function disconnectDevice(deviceId: string) {
    await api.disconnectDevice(deviceId);
    // Remove from local state immediately; WebSocket will confirm
    devices.value = devices.value.filter((d) => d.id !== deviceId);
    specs.value.delete(deviceId);
  }

  async function connectDevice(deviceId: string) {
    const result = await api.connectDevice(deviceId);
    // Refresh device list from response
    if (result.devices) {
      devices.value = result.devices;
      // Load spec for newly connected device
      for (const d of result.devices) {
        if (!specs.value.has(d.id)) {
          void api.getDeviceSpec(d.id).then((spec) => {
            specs.value.set(d.id, spec);
          });
        }
      }
    }
  }

  function selectNode(nodeId: string | null) {
    selectedNodeId.value = nodeId;
  }

  function getDeviceSpec(devicePath: string): DeviceSpec | null {
    return getSpecForPath(devicePath);
  }

  function getPropertySpec(devicePath: string, propName: string): PropertySpec | undefined {
    return getSpecForPath(devicePath)?.properties?.find((p) => p.name === propName);
  }

  function getCommandSpec(devicePath: string, cmdName: string): CommandSpec | undefined {
    return getSpecForPath(devicePath)?.commands?.find((c) => c.name === cmdName);
  }

  function getDataSourceSpec(devicePath: string, sourceName: string): DataSourceSpec | undefined {
    return getSpecForPath(devicePath)?.data_sources?.find((ds) => ds.name === sourceName);
  }

  // WebSocket for real-time updates
  function startEventsListener() {
    if (eventsWs.value) return;

    const ws = api.openEventsWebSocket();
    eventsWs.value = ws;

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);

        if (msg.type === 'snapshot' && Array.isArray(msg.devices)) {
          // Full snapshot - update all devices
          const newIds = new Set(msg.devices.map((d: DeviceState) => d.id));
          devices.value = msg.devices;

          // Load specs for new devices
          for (const d of msg.devices as DeviceState[]) {
            if (!specs.value.has(d.id)) {
              void api.getDeviceSpec(d.id).then((spec) => {
                specs.value.set(d.id, spec);
              });
            }
          }

          // Remove specs for removed devices
          for (const id of specs.value.keys()) {
            if (!newIds.has(id)) {
              specs.value.delete(id);
            }
          }
        } else if (msg.type === 'device.state' && msg.id) {
          // Single device state update
          const idx = devices.value.findIndex((d) => d.id === msg.id);
          const existing = devices.value[idx];
          if (idx !== -1 && existing) {
            devices.value[idx] = {
              id: existing.id,
              driver: existing.driver,
              state: msg.state as Record<string, unknown>,
              // Use status from event if present, otherwise keep existing
              status: ((msg.status as string | undefined) ?? existing.status) as
                | 'connected'
                | 'disconnected'
                | 'unhealthy',
              ...(existing.doc !== undefined ? { doc: existing.doc } : {}),
            };
          }
        }
      } catch {
        // Ignore parse errors
      }
    };

    ws.onerror = () => {
      error.value = 'WebSocket error';
    };

    ws.onclose = () => {
      eventsWs.value = null;
      // Attempt to reconnect after 3 seconds
      setTimeout(() => {
        if (!eventsWs.value) {
          startEventsListener();
        }
      }, 3000);
    };
  }

  function stopEventsListener() {
    if (eventsWs.value) {
      eventsWs.value.close();
      eventsWs.value = null;
    }
  }

  return {
    // State
    devices,
    specs,
    loading,
    error,
    selectedNodeId,

    // Computed
    deviceList,
    deviceMap,
    treeNodes,
    selectedDevice,
    selectedDevicePath,
    selectedSpec,
    selectedNodeType,
    selectedItemName,
    selectedCategoryType,

    // Path helpers (used by panel components)
    getSpecForPath,
    getStateForPath,

    // Actions
    loadDevices,
    updateProperty,
    runCommand,
    disconnectDevice,
    connectDevice,
    selectNode,
    getDeviceSpec,
    getPropertySpec,
    getCommandSpec,
    getDataSourceSpec,
    startEventsListener,
    stopEventsListener,
  };
});
