<template>
  <div class="workspace-panel">
    <div class="workspace-header q-pa-sm">
      <div class="row items-center justify-between">
        <div class="text-subtitle2 text-grey-8">Shelf</div>
        <q-btn
          v-if="workspace.items.length > 0"
          flat
          dense
          size="sm"
          icon="delete_sweep"
          color="grey"
          @click="onClearAll"
        >
          <q-tooltip>Clear all</q-tooltip>
        </q-btn>
      </div>
      <div class="text-caption text-grey-6">Drag properties and commands here</div>
    </div>

    <q-scroll-area class="workspace-scroll">
      <div
        class="workspace-drop-zone"
        :class="{ 'drag-over': isDragOver && !dropTargetIndex }"
        @dragover.prevent="onDragOver"
        @dragleave="onDragLeave"
        @drop="onDrop"
      >
        <div v-if="workspace.items.length === 0" class="empty-message">
          <q-icon name="drag_indicator" size="lg" color="grey-4" />
          <div class="text-caption text-grey-5 q-mt-sm">
            Drop items here to build your working area
          </div>
        </div>

        <div v-else class="workspace-items">
          <!-- Drop zone before first item -->
          <div
            class="drop-indicator"
            :class="{ active: dropTargetIndex === 0 }"
            @dragover.prevent="onDropZoneDragOver(0)"
            @dragleave="onDropZoneDragLeave"
            @drop="onDropZoneDrop($event, 0)"
          ></div>

          <template v-for="(item, index) in workspace.items" :key="item.id">
            <WorkspaceItem
              :item="item"
              :index="index"
              draggable="true"
              @dragstart="onItemDragStart($event, index)"
              @dragend="onItemDragEnd"
              @remove="workspace.removeItem(item.id)"
            />
            <!-- Drop zone after each item -->
            <div
              class="drop-indicator"
              :class="{ active: dropTargetIndex === index + 1 }"
              @dragover.prevent="onDropZoneDragOver(index + 1)"
              @dragleave="onDropZoneDragLeave"
              @drop="onDropZoneDrop($event, index + 1)"
            ></div>
          </template>
        </div>
      </div>
    </q-scroll-area>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useWorkspaceStore } from 'stores/workspace';
import { useQuasar } from 'quasar';
import WorkspaceItem from './WorkspaceItem.vue';

const workspace = useWorkspaceStore();
const $q = useQuasar();
const isDragOver = ref(false);
const dragSourceIndex = ref<number | null>(null);
const dropTargetIndex = ref<number | null>(null);

function onDragOver() {
  // Check if this is an internal reorder drag
  if (dragSourceIndex.value !== null) {
    return;
  }
  isDragOver.value = true;
}

function onDragLeave() {
  isDragOver.value = false;
}

function onDrop(e: DragEvent) {
  isDragOver.value = false;
  dropTargetIndex.value = null;

  // If this is an internal reorder, handle it elsewhere
  if (dragSourceIndex.value !== null) {
    return;
  }

  const data = e.dataTransfer?.getData('application/json');
  if (!data) return;

  try {
    const payload = JSON.parse(data);
    if (payload.type === 'property' || payload.type === 'command' || payload.type === 'macro') {
      // Check duplicate by ID
      const checkId =
        payload.type === 'macro'
          ? `macro:${payload.fileName}:${payload.itemName}`
          : `${payload.deviceId}:${payload.type}:${payload.itemName}`;
      if (workspace.items.some((i) => i.id === checkId)) {
        $q.notify({
          type: 'info',
          message: 'Item already in workspace',
        });
        return;
      }

      workspace.addItem(
        payload.type,
        payload.deviceId || '',
        payload.itemName,
        payload.fileName,
      );
      $q.notify({
        type: 'positive',
        message: `Added ${payload.type} to workspace`,
        timeout: 1500,
      });
    }
  } catch {
    // Ignore invalid data
  }
}

function onItemDragStart(e: DragEvent, index: number) {
  dragSourceIndex.value = index;
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(index));
  }
}

function onItemDragEnd() {
  dragSourceIndex.value = null;
  dropTargetIndex.value = null;
}

function onDropZoneDragOver(index: number) {
  if (dragSourceIndex.value !== null) {
    // Don't highlight if dropping in same position or adjacent position
    if (dragSourceIndex.value !== index && dragSourceIndex.value !== index - 1) {
      dropTargetIndex.value = index;
    }
  }
}

function onDropZoneDragLeave() {
  dropTargetIndex.value = null;
}

function onDropZoneDrop(e: DragEvent, targetIndex: number) {
  e.stopPropagation();

  if (dragSourceIndex.value !== null) {
    // Adjust target index when moving down
    const adjustedTarget = targetIndex > dragSourceIndex.value ? targetIndex - 1 : targetIndex;
    if (dragSourceIndex.value !== adjustedTarget) {
      workspace.moveItem(dragSourceIndex.value, adjustedTarget);
    }
  }

  dragSourceIndex.value = null;
  dropTargetIndex.value = null;
}

function onClearAll() {
  $q.dialog({
    title: 'Clear Workspace',
    message: 'Remove all items from the workspace?',
    cancel: true,
  }).onOk(() => {
    workspace.clearAll();
  });
}
</script>

<style scoped>
.workspace-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.workspace-header {
  border-bottom: 1px solid rgba(0, 0, 0, 0.1);
}

.workspace-scroll {
  flex: 1;
  height: calc(100vh - 110px);
}

.workspace-drop-zone {
  min-height: 200px;
  padding: 8px;
  transition: background-color 0.2s;
}

.workspace-drop-zone.drag-over {
  background-color: rgba(25, 118, 210, 0.08);
}

.empty-message {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 16px;
  text-align: center;
}

.workspace-items {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.drop-indicator {
  height: 4px;
  margin: 2px 0;
  border-radius: 2px;
  background: transparent;
  transition:
    background-color 0.15s,
    height 0.15s;
}

.drop-indicator.active {
  height: 6px;
  background: #1976d2;
}
</style>
