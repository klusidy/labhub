<template>
  <div class="repl-terminal">
    <!-- Header -->
    <div class="terminal-header q-pa-sm bg-grey-9 text-white">
      <div class="row items-center justify-between">
        <div class="row items-center">
          <q-icon name="terminal" size="sm" class="q-mr-xs" />
          <span class="text-subtitle2">Python REPL</span>
          <q-badge
            :color="store.connected ? 'positive' : 'grey'"
            :label="store.connected ? 'Connected' : 'Disconnected'"
            class="q-ml-sm"
          />
        </div>
        <div class="row q-gutter-xs">
          <q-btn
            flat
            dense
            size="sm"
            icon="clear"
            @click="store.clearOutput"
            :disable="!store.connected"
          >
            <q-tooltip>Clear output</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            size="sm"
            icon="stop"
            color="negative"
            @click="handleInterrupt"
            :disable="!store.connected"
          >
            <q-tooltip>Interrupt (Ctrl+C)</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            size="sm"
            :icon="store.connected ? 'link_off' : 'link'"
            @click="toggleConnection"
            :loading="store.connecting"
          >
            <q-tooltip>{{ store.connected ? 'Disconnect' : 'Connect' }}</q-tooltip>
          </q-btn>
        </div>
      </div>
    </div>

    <!-- Output area -->
    <q-scroll-area ref="scrollArea" class="terminal-output bg-blue-grey-10">
      <div class="output-content q-pa-sm">
        <div
          v-for="(line, idx) in store.output"
          :key="idx"
          class="output-line"
          :class="{ 'stderr-line': line.stream === 'stderr' }"
        >
          {{ line.data }}
        </div>
        <div v-if="!store.connected && !store.connecting" class="text-grey-6 q-pa-md">
          Not connected. Click the connect button to start a REPL session.
        </div>
        <div v-if="store.connecting" class="text-grey-6 q-pa-md">
          <q-spinner size="sm" class="q-mr-xs" />
          Connecting...
        </div>
      </div>
    </q-scroll-area>

    <!-- Input area -->
    <div class="terminal-input bg-blue-grey-7">
      <div class="row items-center q-pa-xs">
        <span class="text-white q-mr-xs">&gt;&gt;&gt;</span>
        <q-input
          v-model="command"
          dense
          dark
          borderless
          placeholder="Enter Python code..."
          class="col"
          @keydown="handleKeyDown"
          :disable="!store.connected"
        />
        <q-btn
          flat
          dense
          icon="send"
          color="primary"
          @click="executeCommand"
          :disable="!store.connected || !command.trim()"
        >
          <q-tooltip>Execute (Enter)</q-tooltip>
        </q-btn>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue';
import { useReplStore } from 'stores/repl';
import { QScrollArea } from 'quasar';

const store = useReplStore();
const scrollArea = ref<QScrollArea>();
const command = ref('');
const commandHistory = ref<string[]>([]);
const historyIndex = ref(-1);

// Auto-scroll to bottom when new output arrives
watch(
  () => store.output.length,
  async () => {
    await nextTick();
    if (scrollArea.value) {
      const scrollTarget = scrollArea.value.getScrollTarget();
      scrollTarget.scrollTop = scrollTarget.scrollHeight;
    }
  }
);

// Execute command
function executeCommand() {
  if (!command.value.trim() || !store.connected) {
    return;
  }

  const cmd = command.value;

  // Add to history
  if (cmd.trim()) {
    commandHistory.value.push(cmd);
    historyIndex.value = commandHistory.value.length;
  }

  // Execute
  try {
    store.executeCode(cmd);
    command.value = '';
  } catch (err) {
    console.error('Failed to execute command:', err);
  }
}

// Handle keyboard shortcuts
function handleKeyDown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    executeCommand();
  } else if (event.key === 'ArrowUp') {
    event.preventDefault();
    navigateHistory(-1);
  } else if (event.key === 'ArrowDown') {
    event.preventDefault();
    navigateHistory(1);
  } else if (event.key === 'c' && event.ctrlKey) {
    event.preventDefault();
    handleInterrupt();
  }
}

// Navigate command history
function navigateHistory(direction: number) {
  if (commandHistory.value.length === 0) {
    return;
  }

  historyIndex.value += direction;

  if (historyIndex.value < 0) {
    historyIndex.value = 0;
  } else if (historyIndex.value >= commandHistory.value.length) {
    historyIndex.value = commandHistory.value.length;
    command.value = '';
    return;
  }

  command.value = commandHistory.value[historyIndex.value] || '';
}

// Send interrupt signal
function handleInterrupt() {
  try {
    store.sendInterrupt();
  } catch (err) {
    console.error('Failed to send interrupt:', err);
  }
}

// Toggle connection
async function toggleConnection() {
  if (store.connected) {
    await store.disconnect();
  } else {
    await store.connect();
  }
}
</script>

<style scoped>
.repl-terminal {
  display: flex;
  flex-direction: column;
  height: 100%;
  border: 1px solid rgba(0, 0, 0, 0.12);
}

.terminal-header {
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.terminal-output {
  flex: 1;
  min-height: 0;
  height: 0;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.4;
}

.output-content {
  color: #f5f5f5;
}

.output-line {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  padding: 0;
}

.stderr-line {
  color: #ff5252;
}

.terminal-input {
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
}

:deep(.q-field__control) {
  color: white !important;
}

:deep(.q-field__native) {
  color: white !important;
}

:deep(.q-placeholder) {
  color: rgba(255, 255, 255, 0.5) !important;
}
</style>
