<template>
  <q-tree
    :nodes="nodes as unknown as object[]"
    node-key="id"
    default-expand-all
    :no-nodes-label="loading ? 'Loading...' : 'No devices'"
  >
    <template v-slot:default-header="prop">

      <!-- Root device node -->
      <div v-if="prop.node.nodeType === 'device'" class="row items-center full-width device-row">
        <q-icon :name="prop.node.icon" :color="prop.node.iconColor" size="sm" class="q-mr-sm" />
        <span class="text-weight-medium">{{ prop.node.label }}</span>
        <q-badge class="q-ml-sm" color="grey-7" outline>{{ prop.node.driver }}</q-badge>
      </div>

      <!-- Child device node -->
      <div v-else-if="prop.node.nodeType === 'childDevice'" class="row items-center full-width child-device-row">
        <q-icon name="device_hub" color="blue-grey" size="xs" class="q-mr-xs" />
        <span class="text-weight-medium text-blue-grey-8">{{ prop.node.label }}</span>
      </div>

      <!-- Property node -->
      <div v-else class="row items-center full-width property-row q-py-xs">
        <!-- Policy toggle -->
        <q-btn-toggle
          :model-value="prop.node.policy"
          :options="[
            { value: 'read', slot: 'read' },
            { value: 'write', slot: 'write' },
          ]"
          :disable="prop.node.readOnly"
          dense
          no-caps
          toggle-color="indigo-7"
          size="sm"
          class="policy-toggle q-mr-sm"
          @update:model-value="(v: 'read' | 'write') => onPolicyChange(prop.node.deviceId, prop.node.propName, v)"
        >
          <template v-slot:read>
            <q-icon name="visibility" size="xs" />
            <q-tooltip>Read-only: value is monitored but not restored on load</q-tooltip>
          </template>
          <template v-slot:write>
            <q-icon name="edit" size="xs" />
            <q-tooltip>Write: value is restored when profile is loaded</q-tooltip>
          </template>
        </q-btn-toggle>

        <!-- Read-only indicator -->
        <q-icon
          v-if="prop.node.readOnly"
          name="lock"
          size="xs"
          color="grey-6"
          class="q-mr-xs"
        >
          <q-tooltip>Read-only property (cannot set write policy)</q-tooltip>
        </q-icon>

        <!-- Property name -->
        <span class="property-name q-mr-md">{{ prop.node.propName }}</span>

        <!-- Property value -->
        <span class="property-value text-grey-7">
          {{ formatValue(prop.node.value) }}
        </span>
      </div>
    </template>
  </q-tree>
</template>

<script setup lang="ts">
interface TreeNode {
  id: string;
  label: string;
  icon?: string;
  iconColor?: string;
  driver?: string;
  nodeType: 'device' | 'childDevice' | 'property';
  devicePath?: string;
  deviceId?: string;
  propName?: string;
  value?: unknown;
  policy?: 'read' | 'write';
  readOnly?: boolean;
  children?: TreeNode[] | undefined;
}

defineProps<{
  nodes: TreeNode[];
  loading?: boolean;
}>();

const emit = defineEmits<{
  policyChange: [deviceId: string, propName: string, policy: 'read' | 'write'];
}>();

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return 'null';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') {
    if (Number.isInteger(value)) return value.toString();
    return value.toPrecision(6).replace(/\.?0+$/, '');
  }
  if (typeof value === 'string') return value;
  const str = JSON.stringify(value);
  return str.length > 80 ? str.slice(0, 77) + '...' : str;
}

function onPolicyChange(deviceId: string | undefined, propName: string | undefined, policy: 'read' | 'write') {
  if (deviceId && propName) {
    emit('policyChange', deviceId, propName, policy);
  }
}
</script>

<style scoped>
.device-row {
  padding: 4px 0;
}

.child-device-row {
  padding: 2px 0;
  font-size: 0.9em;
}

.property-row {
  font-size: 0.9em;
}

.property-name {
  font-family: 'Consolas', 'Monaco', monospace;
  min-width: 150px;
}

.property-value {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 0.9em;
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.policy-toggle {
  border: 1px solid #e0e0e0;
  border-radius: 4px;
}

.policy-toggle :deep(.q-btn) {
  padding: 2px 6px;
}
</style>
