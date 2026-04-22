import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

export interface MacroArg {
  name: string;
  type: string;
  required: boolean;
  default?: unknown;
}

export interface MacroFunction {
  name: string;
  args: MacroArg[];
  doc: string | null;
}

export interface MacroFile {
  filename: string;
  functions: MacroFunction[];
  error?: string;
}

export interface MacroTreeNode {
  id: string;
  label: string;
  icon?: string;
  iconColor?: string;
  children?: MacroTreeNode[];
  type?: 'file' | 'function';
}

export const useMacrosStore = defineStore('macros', () => {
  const files = ref<MacroFile[]>([]);
  const loading = ref(false);
  const enabled = ref(false); // Whether macros are enabled on server
  const selectedNodeId = ref<string | null>(null);

  // Tree nodes computed from files
  const treeNodes = computed<MacroTreeNode[]>(() => {
    return files.value.map((file) => {
      const fileNode: MacroTreeNode = {
        id: `file:${file.filename}`,
        label: file.filename,
        icon: file.error ? 'error' : 'description',
        iconColor: file.error ? 'negative' : 'primary',
        type: 'file',
        children: file.functions.map((func) => ({
          id: `func:${file.filename}:${func.name}`,
          label: func.name,
          icon: 'functions',
          iconColor: 'secondary',
          type: 'function',
        })),
      };
      return fileNode;
    });
  });

  // Selected function (if a function node is selected)
  const selectedFunction = computed<
    { file: MacroFile; func: MacroFunction } | null
  >(() => {
    if (!selectedNodeId.value || !selectedNodeId.value.startsWith('func:')) {
      return null;
    }

    const parts = selectedNodeId.value.split(':');
    if (parts.length !== 3) return null;

    const filename = parts[1];
    const funcName = parts[2];

    const file = files.value.find((f) => f.filename === filename);
    if (!file) return null;

    const func = file.functions.find((f) => f.name === funcName);
    if (!func) return null;

    return { file, func };
  });

  // Selected file (if a file node is selected)
  const selectedFile = computed<MacroFile | null>(() => {
    if (!selectedNodeId.value || !selectedNodeId.value.startsWith('file:')) {
      return null;
    }

    const filename = selectedNodeId.value.substring(5); // Remove 'file:' prefix
    return files.value.find((f) => f.filename === filename) || null;
  });

  async function loadMacros() {
    loading.value = true;
    try {
      const response = await fetch('/api/v2/macros');
      if (response.status === 503) {
        // Macros not configured
        enabled.value = false;
        files.value = [];
        return;
      }

      if (!response.ok) {
        throw new Error(`Failed to load macros: ${response.statusText}`);
      }

      enabled.value = true;
      files.value = await response.json();
    } catch (err) {
      console.error('Failed to load macros:', err);
      enabled.value = false;
      files.value = [];
    } finally {
      loading.value = false;
    }
  }

  async function refresh() {
    try {
      const response = await fetch('/api/v2/macros/refresh', {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error(`Failed to refresh macros: ${response.statusText}`);
      }

      // Reload macros after refresh
      await loadMacros();
    } catch (err) {
      console.error('Failed to refresh macros:', err);
    }
  }

  // File editing state
  const fileContent = ref<string>('');
  const fileContentLoading = ref(false);
  const fileContentDirty = ref(false);
  const fileSaving = ref(false);

  function selectNode(nodeId: string | null) {
    selectedNodeId.value = nodeId;
    fileContentDirty.value = false;
    // Load file content when a file node is selected
    if (nodeId && nodeId.startsWith('file:')) {
      const filename = nodeId.substring(5);
      void loadFileContent(filename);
    }
  }

  async function loadFileContent(filename: string) {
    fileContentLoading.value = true;
    try {
      const response = await fetch(`/api/v2/macros/files/${encodeURIComponent(filename)}`);
      if (!response.ok) {
        throw new Error(`Failed to load file: ${response.statusText}`);
      }
      const data = await response.json();
      fileContent.value = data.content;
      fileContentDirty.value = false;
    } catch (err) {
      console.error('Failed to load file content:', err);
      fileContent.value = '';
    } finally {
      fileContentLoading.value = false;
    }
  }

  function updateFileContent(content: string) {
    fileContent.value = content;
    fileContentDirty.value = true;
  }

  async function saveFileContent(filename: string) {
    fileSaving.value = true;
    try {
      const response = await fetch(`/api/v2/macros/files/${encodeURIComponent(filename)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: fileContent.value }),
      });
      if (!response.ok) {
        throw new Error(`Failed to save file: ${response.statusText}`);
      }
      fileContentDirty.value = false;
      // Refresh to re-parse functions
      await refresh();
    } catch (err) {
      console.error('Failed to save file:', err);
      throw err;
    } finally {
      fileSaving.value = false;
    }
  }

  async function createFile(filename: string) {
    const response = await fetch(`/api/v2/macros/files/${encodeURIComponent(filename)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!response.ok) {
      throw new Error(`Failed to create file: ${response.statusText}`);
    }
    await loadMacros();
    selectNode(`file:${filename}`);
  }

  async function deleteFile(filename: string) {
    const response = await fetch(`/api/v2/macros/files/${encodeURIComponent(filename)}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      throw new Error(`Failed to delete file: ${response.statusText}`);
    }
    if (selectedNodeId.value?.includes(filename)) {
      selectedNodeId.value = null;
    }
    await loadMacros();
  }

  async function renameFile(oldName: string, newName: string) {
    const response = await fetch(
      `/api/v2/macros/files/${encodeURIComponent(oldName)}/rename`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_name: newName }),
      }
    );
    if (!response.ok) {
      throw new Error(`Failed to rename file: ${response.statusText}`);
    }
    await loadMacros();
    selectNode(`file:${newName}`);
  }

  // Get a MacroFunction by filename and function name (for workspace)
  function getMacroFunction(
    filename: string,
    funcName: string,
  ): { file: MacroFile; func: MacroFunction } | null {
    const file = files.value.find((f) => f.filename === filename);
    if (!file) return null;
    const func = file.functions.find((f) => f.name === funcName);
    if (!func) return null;
    return { file, func };
  }

  return {
    files,
    loading,
    enabled,
    selectedNodeId,
    treeNodes,
    selectedFunction,
    selectedFile,
    fileContent,
    fileContentLoading,
    fileContentDirty,
    fileSaving,
    loadMacros,
    refresh,
    selectNode,
    loadFileContent,
    updateFileContent,
    saveFileContent,
    createFile,
    deleteFile,
    renameFile,
    getMacroFunction,
  };
});
