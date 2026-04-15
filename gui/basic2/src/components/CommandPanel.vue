<template>
  <q-card flat bordered class="command-panel">
    <q-card-section class="q-pa-none">
      <div v-if="commands.length === 0" class="text-grey q-pa-sm">No commands available</div>

      <q-expansion-item
        v-for="cmd in commands"
        :key="cmd.name"
        switch-toggle-side
        header-class="command-header bg-light-blue-10 text-white"
      >
        <template #header>
          <div class="row items-center full-width no-wrap q-gutter-sm">
            <q-icon name="bolt" color="white" size="sm" />
            <div class="col">
              <span class="text-weight-medium text-body2">{{ cmd.name }}</span>
              <span class="text-light-blue-3 q-ml-sm text-caption"
                >({{ formatSignature(cmd) }})</span
              >
              <q-tooltip v-if="cmd.doc" anchor="top middle" self="bottom middle">
                {{ cmd.doc }}
              </q-tooltip>
            </div>
            <q-btn
              unelevated
              no-caps
              color="white"
              text-color="light-blue-10"
              label="Run"
              padding="4px 16px"
              :loading="runningCmd === cmd.name"
              @click.stop="onRun(cmd)"
            />
            <q-btn
              flat
              round
              icon="drag_indicator"
              size="sm"
              color="white"
              draggable="true"
              @dragstart="(e: DragEvent) => onDragStart(e, cmd)"
              @click.stop
            >
              <q-tooltip>Drag to shelf</q-tooltip>
            </q-btn>
          </div>
        </template>

        <q-card flat class="command-content">
          <q-card-section v-if="hasArgs(cmd)" class="q-py-sm">
            <div class="text-caption text-weight-medium q-mb-xs">Arguments</div>
            <div v-for="arg in cmd.args" :key="arg.name" class="row items-center q-mb-xs">
              <div class="col-4">
                <span class="text-weight-medium">{{ arg.name }}</span>
                <span v-if="arg.required" class="text-negative">*</span>
                <q-tooltip v-if="arg.doc">{{ arg.doc }}</q-tooltip>
              </div>
              <div class="col-2 text-caption text-grey-6">
                {{ arg.type || 'Any' }}
              </div>
              <div class="col-6">
                <ArgInput
                  :arg="arg"
                  :value="argValues[cmd.name]?.[arg.name]"
                  @update="(v) => setArg(cmd.name, arg.name, v)"
                />
              </div>
            </div>
          </q-card-section>
          <q-card-section v-else class="text-grey q-py-sm text-caption">
            No arguments
          </q-card-section>

          <q-card-section v-if="cmdResults[cmd.name]" class="q-py-sm">
            <div class="text-caption text-weight-medium">Result</div>
            <pre class="result-box">{{ formatResult(cmdResults[cmd.name]) }}</pre>
          </q-card-section>

          <q-card-section v-if="cmdErrors[cmd.name]" class="q-py-sm">
            <div class="text-caption text-weight-medium text-negative">Error</div>
            <pre class="error-box">{{ cmdErrors[cmd.name] }}</pre>
          </q-card-section>
        </q-card>
      </q-expansion-item>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue';
import { useDevicesStore } from 'stores/devices';
import ArgInput from './ArgInput.vue';
import type { CommandSpec, CommandArg } from 'src/api/devices';

const props = defineProps<{
  deviceId: string;
  filterCmd?: string; // If provided, only show this command
}>();

const store = useDevicesStore();
const spec = computed(() => store.getSpecForPath(props.deviceId));

const commands = computed(() => {
  const all = spec.value?.commands || [];
  if (props.filterCmd) {
    return all.filter((c) => c.name === props.filterCmd);
  }
  return all;
});

const argValues = reactive<Record<string, Record<string, unknown>>>({});
const cmdResults = reactive<Record<string, unknown>>({});
const cmdErrors = reactive<Record<string, string>>({});
const runningCmd = ref<string | null>(null);

function hasArgs(cmd: CommandSpec): boolean {
  return Array.isArray(cmd.args) && cmd.args.length > 0;
}

function formatSignature(cmd: CommandSpec): string {
  if (!cmd.args?.length) return '';
  return cmd.args.map((a) => `${a.type || 'Any'} ${a.name}${a.required ? '*' : ''}`).join(', ');
}

function setArg(cmdName: string, argName: string, value: unknown) {
  if (!argValues[cmdName]) {
    argValues[cmdName] = {};
  }
  argValues[cmdName][argName] = value;
}

function buildArgs(cmd: CommandSpec): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const arg of cmd.args || []) {
    const val = argValues[cmd.name]?.[arg.name];
    // Fall back to arg.default if user hasn't touched the input
    const effective = val !== undefined ? val : arg.default;
    result[arg.name] = coerceArg(arg, effective);
  }
  return result;
}

function coerceArg(arg: CommandArg, value: unknown): unknown {
  if (value === '' && !arg.required) return null;
  switch (arg.type) {
    case 'int': {
      const n = parseInt(String(value), 10);
      return Number.isFinite(n) ? n : null;
    }
    case 'float': {
      const n = parseFloat(String(value));
      return Number.isFinite(n) ? n : null;
    }
    case 'bool':
      return !!value;
    default:
      return value;
  }
}

async function onRun(cmd: CommandSpec) {
  runningCmd.value = cmd.name;
  delete cmdResults[cmd.name];
  delete cmdErrors[cmd.name];

  try {
    const args = buildArgs(cmd);
    const result = await store.runCommand(props.deviceId, cmd.name, args);
    cmdResults[cmd.name] = result;
  } catch (e) {
    cmdErrors[cmd.name] = e instanceof Error ? e.message : String(e);
  } finally {
    runningCmd.value = null;
  }
}

function formatResult(r: unknown): string {
  try {
    return JSON.stringify(r, null, 2);
  } catch {
    return String(r);
  }
}

function onDragStart(e: DragEvent, cmd: CommandSpec) {
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'copy';
    e.dataTransfer.setData(
      'application/json',
      JSON.stringify({
        type: 'command',
        deviceId: props.deviceId,
        itemName: cmd.name,
      }),
    );
  }
}
</script>

<style scoped>
.command-panel {
  margin-bottom: 12px;
}

.command-header {
  min-height: 44px;
  padding: 6px 12px;
}

:deep(.q-expansion-item__toggle-icon) {
  color: white;
}

.command-content {
  background: white;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
}

.result-box {
  background: #f5f5f5;
  border: 1px solid #eee;
  border-radius: 4px;
  padding: 6px;
  max-height: 150px;
  overflow: auto;
  font-size: 12px;
  margin: 0;
}

.error-box {
  background: #fff5f5;
  border: 1px solid #fdd;
  border-radius: 4px;
  padding: 6px;
  color: #c00;
  font-size: 12px;
  margin: 0;
}
</style>
