<template>
  <div class="macro-tree">
    <div class="tree-header q-pa-sm">
      <div class="row items-center justify-between">
        <div class="text-subtitle2 text-grey-8">Macros</div>
        <div>
          <q-btn flat dense size="sm" icon="add" @click="showCreateDialog = true" :disable="!store.enabled">
            <q-tooltip>New macro file</q-tooltip>
          </q-btn>
          <q-btn flat dense size="sm" icon="refresh" @click="refreshMacros">
            <q-tooltip>Refresh macro list</q-tooltip>
          </q-btn>
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
      <div v-if="!store.enabled" class="q-pa-md text-center text-grey">
        <q-icon name="info" size="sm" class="q-mr-xs" />
        <div class="text-caption">Macros not configured</div>
      </div>

      <q-tree
        v-else
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
            class="row items-center tree-node full-width"
            :class="{ 'selected-node': prop.node.id === selectedNode }"
          >
            <q-icon
              v-if="prop.node.icon"
              :name="prop.node.icon"
              :color="prop.node.iconColor"
              size="xs"
              class="q-mr-xs"
            />
            <span class="tree-label col">{{ prop.node.label }}</span>
            <!-- Context menu for file nodes -->
            <q-menu v-if="prop.node.type === 'file'" context-menu>
              <q-list dense style="min-width: 120px">
                <q-item clickable v-close-popup @click="startRename(prop.node.label)">
                  <q-item-section avatar><q-icon name="edit" size="xs" /></q-item-section>
                  <q-item-section>Rename</q-item-section>
                </q-item>
                <q-item clickable v-close-popup @click="confirmDelete(prop.node.label)">
                  <q-item-section avatar><q-icon name="delete" size="xs" color="negative" /></q-item-section>
                  <q-item-section class="text-negative">Delete</q-item-section>
                </q-item>
              </q-list>
            </q-menu>
          </div>
        </template>
      </q-tree>

      <div v-if="store.loading" class="q-pa-sm text-center text-grey">
        <q-spinner size="sm" class="q-mr-xs" />
        Loading...
      </div>

      <div
        v-if="!store.loading && store.enabled && filteredNodes.length === 0"
        class="q-pa-sm text-center text-grey"
      >
        No macros found
      </div>
    </q-scroll-area>

    <!-- Create file dialog -->
    <q-dialog v-model="showCreateDialog">
      <q-card style="min-width: 300px">
        <q-card-section>
          <div class="text-h6">New Macro File</div>
        </q-card-section>
        <q-card-section>
          <q-input
            v-model="newFileName"
            dense
            outlined
            label="Filename"
            hint="Must end with .py"
            :rules="[
              (v) => !!v || 'Required',
              (v) => v.endsWith('.py') || 'Must end with .py',
            ]"
            @keydown.enter="createFile"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Cancel" v-close-popup />
          <q-btn
            unelevated
            color="primary"
            label="Create"
            :disable="!newFileName || !newFileName.endsWith('.py')"
            @click="createFile"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Rename dialog -->
    <q-dialog v-model="showRenameDialog">
      <q-card style="min-width: 300px">
        <q-card-section>
          <div class="text-h6">Rename File</div>
          <div class="text-caption text-grey">{{ renameOldName }}</div>
        </q-card-section>
        <q-card-section>
          <q-input
            v-model="renameNewName"
            dense
            outlined
            label="New filename"
            hint="Must end with .py"
            :rules="[
              (v) => !!v || 'Required',
              (v) => v.endsWith('.py') || 'Must end with .py',
            ]"
            @keydown.enter="renameFile"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Cancel" v-close-popup />
          <q-btn
            unelevated
            color="primary"
            label="Rename"
            :disable="!renameNewName || !renameNewName.endsWith('.py')"
            @click="renameFile"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useQuasar } from 'quasar';
import { useMacrosStore, type MacroTreeNode } from 'stores/macros';
import { useDevicesStore } from 'stores/devices';

const $q = useQuasar();
const store = useMacrosStore();
const devicesStore = useDevicesStore();
const treeRef = ref();
const filter = ref('');

// Create dialog state
const showCreateDialog = ref(false);
const newFileName = ref('');

// Rename dialog state
const showRenameDialog = ref(false);
const renameOldName = ref('');
const renameNewName = ref('');

const selectedNode = computed({
  get: () => store.selectedNodeId,
  set: (val) => store.selectNode(val),
});

const filteredNodes = computed(() => store.treeNodes);

function filterMethod(node: MacroTreeNode, filter: string): boolean {
  const f = filter.toLowerCase();
  if (node.label.toLowerCase().includes(f)) return true;
  if (node.children) {
    return node.children.some((c) => filterMethod(c, filter));
  }
  return false;
}

function onSelect(nodeId: string | null) {
  if (nodeId) {
    devicesStore.selectNode(null);
  }
  store.selectNode(nodeId);
}

function expandAll() {
  treeRef.value?.expandAll();
}

function collapseAll() {
  treeRef.value?.collapseAll();
}

async function refreshMacros() {
  await store.refresh();
}

async function createFile() {
  if (!newFileName.value || !newFileName.value.endsWith('.py')) return;
  try {
    await store.createFile(newFileName.value);
    showCreateDialog.value = false;
    newFileName.value = '';
    $q.notify({ type: 'positive', message: 'File created', timeout: 1500 });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    $q.notify({ type: 'negative', message: `Failed to create file: ${msg}` });
  }
}

function startRename(filename: string) {
  renameOldName.value = filename;
  renameNewName.value = filename;
  showRenameDialog.value = true;
}

async function renameFile() {
  if (!renameNewName.value || !renameNewName.value.endsWith('.py')) return;
  try {
    await store.renameFile(renameOldName.value, renameNewName.value);
    showRenameDialog.value = false;
    $q.notify({ type: 'positive', message: 'File renamed', timeout: 1500 });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    $q.notify({ type: 'negative', message: `Failed to rename file: ${msg}` });
  }
}

function confirmDelete(filename: string) {
  $q.dialog({
    title: 'Delete Macro File',
    message: `Are you sure you want to delete "${filename}"? This cannot be undone.`,
    cancel: true,
    persistent: true,
  }).onOk(() => {
    store.deleteFile(filename).then(() => {
      $q.notify({ type: 'positive', message: 'File deleted', timeout: 1500 });
    }).catch((e: unknown) => {
      const msg = e instanceof Error ? e.message : String(e);
      $q.notify({ type: 'negative', message: `Failed to delete file: ${msg}` });
    });
  });
}
</script>

<style scoped>
.macro-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
  border-top: 1px solid rgba(0, 0, 0, 0.1);
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
