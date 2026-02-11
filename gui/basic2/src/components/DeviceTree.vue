<template>
  <div class="device-tree">
    <div class="tree-header q-pa-sm">
      <div class="row items-center justify-between">
        <div class="text-subtitle2 text-grey-8">Devices</div>
        <div>
          <q-btn flat dense size="sm" icon="unfold_less" @click="collapseAll">
            <q-tooltip>Collapse all</q-tooltip>
          </q-btn>
          <q-btn flat dense size="sm" icon="unfold_more" @click="expandAll">
            <q-tooltip>Expand all</q-tooltip>
          </q-btn>
        </div>
      </div>
      <q-input v-model="filter" dense outlined placeholder="Filter..." class="q-mt-xs">
        <template #prepend>
          <q-icon name="search" size="xs" />
        </template>
        <template #append v-if="filter">
          <q-icon name="close" size="xs" class="cursor-pointer" @click="filter = ''" />
        </template>
      </q-input>
    </div>

    <q-scroll-area class="tree-scroll">
      <q-tree
        ref="treeRef"
        :nodes="filteredNodes as unknown as object[]"
        node-key="id"
        v-model:selected="selectedNode"
        :filter="filter"
        :filter-method="filterMethod"
        default-expand-all
        dense
        @update:selected="onSelect"
      >
        <template #default-header="prop">
          <div
            class="row items-center tree-node"
            :class="{ 'selected-node': prop.node.id === selectedNode }"
          >
            <q-icon
              v-if="prop.node.icon"
              :name="prop.node.icon"
              :color="prop.node.iconColor"
              size="xs"
              class="q-mr-xs"
            />
            <span class="tree-label">{{ prop.node.label }}</span>
          </div>
        </template>
      </q-tree>

      <div v-if="store.loading" class="q-pa-sm text-center text-grey">
        <q-spinner size="sm" class="q-mr-xs" />
        Loading...
      </div>

      <div
        v-if="!store.loading && filteredNodes.length === 0"
        class="q-pa-sm text-center text-grey"
      >
        No devices found
      </div>
    </q-scroll-area>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useDevicesStore, type TreeNode } from 'stores/devices';
import { useMacrosStore } from 'stores/macros';

const store = useDevicesStore();
const macrosStore = useMacrosStore();
const treeRef = ref();
const filter = ref('');

const selectedNode = computed({
  get: () => store.selectedNodeId,
  set: (val) => store.selectNode(val),
});

const filteredNodes = computed(() => store.treeNodes);

function filterMethod(node: TreeNode, filter: string): boolean {
  const f = filter.toLowerCase();
  if (node.label.toLowerCase().includes(f)) return true;
  // Also match children
  if (node.children) {
    return node.children.some((c) => filterMethod(c, filter));
  }
  return false;
}

function onSelect(nodeId: string | null) {
  if (nodeId) {
    macrosStore.selectNode(null);
  }
  store.selectNode(nodeId);
}

function expandAll() {
  treeRef.value?.expandAll();
}

function collapseAll() {
  treeRef.value?.collapseAll();
}
</script>

<style scoped>
.device-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.tree-header {
  border-bottom: 1px solid rgba(0, 0, 0, 0.1);
}

.tree-scroll {
  flex: 1;
  min-height: 0;
}

.tree-node {
  padding: 1px 4px;
  border-radius: 3px;
  margin: -1px 0;
}

.tree-node.selected-node {
  background-color: #e3f2fd; /* light-blue-2 */
  color: #0d47a1; /* dark blue */
  font-weight: 500;
}

.tree-label {
  font-size: 13px;
}

:deep(.q-tree__node-header) {
  padding: 2px 4px;
}

:deep(.q-tree__node) {
  padding: 0;
}
</style>
