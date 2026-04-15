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
  path: string;   // full API path, e.g. 'ps5000a' or 'ps5000a/ch_a'
  label: string;  // last path segment for display
  driver: string;
  status: 'connected' | 'disconnected' | 'unhealthy';
  properties: Record<string, PropertyData>;
  children: Record<string, DeviceData>;
}

export const useProfileStore = defineStore('profile', () => {
  // State
  const profilePath = ref<string | null>(null);
  const rawProfile = ref<string>('');
  const devices = ref<DeviceData[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  // --- Tree node types ---

  interface TreeNode {
    id: string;
    label: string;
    icon?: string;
    iconColor?: string;
    driver?: string;
    nodeType: 'device' | 'childDevice' | 'property';
    devicePath?: string;
    deviceId?: string;   // alias for devicePath (used by property nodes)
    propName?: string;
    value?: unknown;
    policy?: 'read' | 'write';
    readOnly?: boolean;
    selectable?: boolean;
    children?: TreeNode[] | undefined;
  }

  function buildDeviceNode(dev: DeviceData): TreeNode {
    const childDeviceNodes: TreeNode[] = Object.values(dev.children).map((child) =>
      buildChildDeviceNode(child),
    );

    const propNodes: TreeNode[] = Object.entries(dev.properties).map(([propName, propData]) => ({
      label: propName,
      id: `${dev.path}::${propName}`,
      nodeType: 'property' as const,
      deviceId: dev.path,
      propName,
      value: propData.value,
      policy: propData.policy,
      readOnly: propData.readOnly,
      selectable: false,
    }));

    const children = [...childDeviceNodes, ...propNodes];

    return {
      label: dev.label,
      id: dev.path,
      icon: getDeviceIcon(dev.status),
      iconColor: getDeviceColor(dev.status),
      driver: dev.driver,
      nodeType: 'device',
      devicePath: dev.path,
      selectable: false,
      children: children.length > 0 ? children : undefined,
    };
  }

  function buildChildDeviceNode(dev: DeviceData): TreeNode {
    const childDeviceNodes: TreeNode[] = Object.values(dev.children).map((child) =>
      buildChildDeviceNode(child),
    );

    const propNodes: TreeNode[] = Object.entries(dev.properties).map(([propName, propData]) => ({
      label: propName,
      id: `${dev.path}::${propName}`,
      nodeType: 'property' as const,
      deviceId: dev.path,
      propName,
      value: propData.value,
      policy: propData.policy,
      readOnly: propData.readOnly,
      selectable: false,
    }));

    const children = [...childDeviceNodes, ...propNodes];

    return {
      label: dev.label,
      id: dev.path,
      icon: 'device_hub',
      iconColor: 'blue-grey',
      nodeType: 'childDevice',
      devicePath: dev.path,
      selectable: false,
      children: children.length > 0 ? children : undefined,
    };
  }

  // Computed - tree nodes for q-tree
  const treeNodes = computed<TreeNode[]>(() => devices.value.map(buildDeviceNode));

  // Helper functions
  function getDeviceIcon(status: string): string {
    switch (status) {
      case 'connected': return 'check_circle';
      case 'disconnected': return 'cancel';
      case 'unhealthy': return 'warning';
      default: return 'help_outline';
    }
  }

  function getDeviceColor(status: string): string {
    switch (status) {
      case 'connected': return 'indigo-9';
      case 'disconnected': return 'negative';
      case 'unhealthy': return 'warning';
      default: return 'grey';
    }
  }

  // Build a DeviceData for a root DeviceState, recursing into spec.children
  function buildDeviceData(
    path: string,
    label: string,
    driver: string,
    status: 'connected' | 'disconnected' | 'unhealthy',
    state: Record<string, unknown>,
    spec: DeviceSpec | null,
    policies: Record<string, string>,
  ): DeviceData {
    const properties: Record<string, PropertyData> = {};
    const specProps = spec?.properties ?? {};

    // Own properties: keys in state that are NOT sub-dicts belonging to a child device
    const childKeys = new Set(Object.keys(spec?.children ?? {}));
    for (const [propName, value] of Object.entries(state)) {
      if (childKeys.has(propName)) continue; // skip child-device state blobs
      const policy = (policies[propName] as 'read' | 'write') ?? (specProps[propName]?.read_only ? 'read' : 'write');
      properties[propName] = {
        value,
        policy,
        readOnly: specProps[propName]?.read_only ?? false,
      };
    }

    // Recurse into children
    const children: Record<string, DeviceData> = {};
    if (spec?.children) {
      for (const [childId, childSpec] of Object.entries(spec.children)) {
        const childPath = `${path}/${childId}`;
        const childState = (state[childId] as Record<string, unknown>) ?? {};
        const childPolicies = (policies[childId] as unknown as Record<string, string>) ?? {};
        children[childId] = buildDeviceData(
          childPath,
          childId,
          driver,
          status,
          childState,
          childSpec,
          childPolicies,
        );
      }
    }

    return { path, label, driver, status, properties, children };
  }

  // Actions
  async function loadProfile() {
    loading.value = true;
    error.value = null;
    try {
      const profile = await api.getProfile();
      profilePath.value = profile.path;
      rawProfile.value = profile.raw;

      const deviceStates = await api.listDevices();
      const deviceDataList: DeviceData[] = [];

      for (const devState of deviceStates) {
        let spec: DeviceSpec | null = null;
        try {
          spec = await api.getDeviceSpec(devState.id);
        } catch {
          // spec unavailable
        }

        // policies for this root device (may include nested path keys from child entries)
        const rootPolicies = profile.policies[devState.id] ?? {};
        // also collect child policies keyed by child path
        const allPolicies: Record<string, unknown> = { ...rootPolicies };
        for (const [policyKey, policyVal] of Object.entries(profile.policies)) {
          if (policyKey.startsWith(devState.id + '/')) {
            // e.g. "ps5000a/ch_a" → nest under the child key
            const childRelPath = policyKey.slice(devState.id.length + 1);
            const parts = childRelPath.split('/');
            // build nested policy dict matching state structure
            let cursor = allPolicies;
            for (let i = 0; i < parts.length - 1; i++) {
              const p = parts[i]!;
              if (!cursor[p] || typeof cursor[p] !== 'object') cursor[p] = {};
              cursor = cursor[p] as Record<string, unknown>;
            }
            const lastPart = parts[parts.length - 1]!;
            // merge child's prop policies
            cursor[lastPart] = policyVal;
          }
        }

        deviceDataList.push(
          buildDeviceData(
            devState.id,
            devState.id,
            devState.driver,
            devState.status,
            devState.state,
            spec,
            allPolicies as Record<string, string>,
          ),
        );
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
    devicePath: string,
    propName: string,
    policy: 'read' | 'write',
  ) {
    loading.value = true;
    try {
      await api.setPropertyPolicy(devicePath, propName, policy);

      // Update local state by walking the device tree
      updatePolicyLocal(devices.value, devicePath, propName, policy);

      // Refresh raw profile
      const profile = await api.getProfile();
      rawProfile.value = profile.raw;
    } finally {
      loading.value = false;
    }
  }

  function updatePolicyLocal(
    devList: DeviceData[],
    targetPath: string,
    propName: string,
    policy: 'read' | 'write',
  ) {
    for (const dev of devList) {
      if (dev.path === targetPath) {
        if (dev.properties[propName]) {
          dev.properties[propName].policy = policy;
        }
        return;
      }
      // recurse into children
      updatePolicyLocal(Object.values(dev.children), targetPath, propName, policy);
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
