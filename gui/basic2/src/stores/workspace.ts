import { defineStore } from 'pinia';
import { ref, watch } from 'vue';

export interface WorkspaceItem {
  id: string; // Unique ID for the item in workspace
  type: 'property' | 'command' | 'macro';
  deviceId: string;
  itemName: string;
  fileName?: string; // For macros: the source file
  addedAt: number;
}

const STORAGE_KEY = 'labhub-workspace-items';

function loadFromStorage(): WorkspaceItem[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      return JSON.parse(stored);
    }
  } catch {
    // Ignore parse errors
  }
  return [];
}

function saveToStorage(items: WorkspaceItem[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    // Ignore storage errors
  }
}

export const useWorkspaceStore = defineStore('workspace', () => {
  // State - load from localStorage on init
  const items = ref<WorkspaceItem[]>(loadFromStorage());

  // Watch for changes and persist to localStorage
  watch(
    items,
    (newItems) => {
      saveToStorage(newItems);
    },
    { deep: true }
  );

  // Actions
  function addItem(
    type: 'property' | 'command' | 'macro',
    deviceId: string,
    itemName: string,
    fileName?: string,
  ) {
    const existingId =
      type === 'macro'
        ? `macro:${fileName}:${itemName}`
        : `${deviceId}:${type}:${itemName}`;
    if (items.value.some((i) => i.id === existingId)) {
      return; // Don't add duplicates
    }

    const item: WorkspaceItem = {
      id: existingId,
      type,
      deviceId,
      itemName,
      addedAt: Date.now(),
    };
    if (fileName !== undefined) {
      item.fileName = fileName;
    }
    items.value.push(item);
  }

  function removeItem(itemId: string) {
    const idx = items.value.findIndex((i) => i.id === itemId);
    if (idx !== -1) {
      items.value.splice(idx, 1);
    }
  }

  function moveItem(fromIndex: number, toIndex: number) {
    if (
      fromIndex < 0 ||
      fromIndex >= items.value.length ||
      toIndex < 0 ||
      toIndex >= items.value.length
    ) {
      return;
    }
    const removed = items.value.splice(fromIndex, 1);
    const item = removed[0];
    if (item !== undefined) {
      items.value.splice(toIndex, 0, item);
    }
  }

  function clearAll() {
    items.value = [];
  }

  function hasItem(deviceId: string, type: string, itemName: string): boolean {
    const id = `${deviceId}:${type}:${itemName}`;
    return items.value.some((i) => i.id === id);
  }

  return {
    // State
    items,

    // Actions
    addItem,
    removeItem,
    moveItem,
    clearAll,
    hasItem,
  };
});
