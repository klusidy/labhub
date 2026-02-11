<template>
  <q-card flat bordered class="macro-panel">
    <q-card-section class="q-pa-none">
      <div v-if="functions.length === 0" class="text-grey q-pa-sm">
        No macro functions available
      </div>

      <q-expansion-item
        v-for="func in functions"
        :key="func.name"
        switch-toggle-side
        header-class="macro-header bg-pink-9 text-white"
      >
        <template #header>
          <div class="row items-center full-width no-wrap q-gutter-sm">
            <q-icon name="functions" color="white" size="sm" />
            <div class="col">
              <span class="text-weight-medium text-body2">{{ func.name }}</span>
              <span class="text-pink-3 q-ml-sm text-caption"
                >({{ formatSignature(func) }})</span
              >
              <q-tooltip v-if="func.doc" anchor="top middle" self="bottom middle">
                {{ func.doc }}
              </q-tooltip>
            </div>
            <q-btn
              unelevated
              no-caps
              color="white"
              text-color="pink-9"
              label="Run"
              padding="4px 16px"
              :loading="runningFunc === func.name"
              @click.stop="onRun(func)"
            />
            <q-btn
              flat
              round
              icon="drag_indicator"
              size="sm"
              color="white"
              draggable="true"
              @dragstart="(e: DragEvent) => onDragStart(e, func)"
              @click.stop
            >
              <q-tooltip>Drag to shelf</q-tooltip>
            </q-btn>
          </div>
        </template>

        <q-card flat class="macro-content">
          <q-card-section v-if="func.doc" class="q-py-sm">
            <div class="text-body2 text-grey-8" style="white-space: pre-wrap">
              {{ func.doc }}
            </div>
          </q-card-section>

          <q-card-section v-if="hasArgs(func)" class="q-py-sm">
            <div class="text-caption text-weight-medium q-mb-xs">Arguments</div>
            <div v-for="arg in func.args" :key="arg.name" class="row items-center q-mb-xs">
              <div class="col-4">
                <span class="text-weight-medium">{{ arg.name }}</span>
                <span v-if="arg.required" class="text-negative">*</span>
              </div>
              <div class="col-2 text-caption text-grey-6">
                {{ arg.type || 'Any' }}
              </div>
              <div class="col-6">
                <ArgInput
                  :arg="toCommandArg(arg)"
                  :value="argValues[func.name]?.[arg.name]"
                  @update="(v) => setArg(func.name, arg.name, v)"
                />
              </div>
            </div>
          </q-card-section>
          <q-card-section v-else class="text-grey q-py-sm text-caption">
            No arguments
          </q-card-section>
        </q-card>
      </q-expansion-item>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue';
import { useMacrosStore, type MacroFunction, type MacroArg } from 'stores/macros';
import { useReplStore } from 'stores/repl';
import ArgInput from './ArgInput.vue';
import type { CommandArg } from 'src/api/devices';

const props = defineProps<{
  filename: string;
  filterFunc?: string;
}>();

const macrosStore = useMacrosStore();
const replStore = useReplStore();

const functions = computed(() => {
  const file = macrosStore.files.find((f) => f.filename === props.filename);
  if (!file) return [];
  if (props.filterFunc) {
    return file.functions.filter((f) => f.name === props.filterFunc);
  }
  return file.functions;
});

const argValues = reactive<Record<string, Record<string, unknown>>>({});
const runningFunc = ref<string | null>(null);

function hasArgs(func: MacroFunction): boolean {
  return Array.isArray(func.args) && func.args.length > 0;
}

function formatSignature(func: MacroFunction): string {
  if (!func.args?.length) return '';
  return func.args
    .map((a) => `${a.type || 'Any'} ${a.name}${a.required ? '*' : ''}`)
    .join(', ');
}

// Convert MacroArg to CommandArg for ArgInput compatibility
function toCommandArg(arg: MacroArg): CommandArg {
  const result: CommandArg = {
    name: arg.name,
    required: arg.required,
    default: arg.default,
  };
  if (arg.type && ['int', 'float', 'bool', 'str'].includes(arg.type)) {
    result.type = arg.type as 'int' | 'float' | 'bool' | 'str';
  }
  return result;
}

function setArg(funcName: string, argName: string, value: unknown) {
  if (!argValues[funcName]) {
    argValues[funcName] = {};
  }
  argValues[funcName][argName] = value;
}

function formatPythonValue(arg: MacroArg, value: unknown): string {
  if (value === null || value === undefined || value === '') {
    if (!arg.required && arg.default !== undefined) {
      return ''; // skip, use default
    }
    return 'None';
  }
  const t = arg.type?.toLowerCase() || '';
  if (t === 'bool') {
    return value ? 'True' : 'False';
  }
  if (t === 'int' || t === 'float') {
    return String(value as number);
  }
  // String: escape quotes
  const s = String(value as string | number);
  return `'${s.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;
}

function buildPythonCall(func: MacroFunction): string {
  const args: string[] = [];
  for (const arg of func.args) {
    const val = argValues[func.name]?.[arg.name];
    if (val === undefined || val === null || val === '') {
      if (!arg.required) continue; // skip optional args without values
    }
    const pyVal = formatPythonValue(arg, val);
    if (pyVal === '') continue;
    args.push(`${arg.name}=${pyVal}`);
  }
  return `${func.name}(${args.join(', ')})`;
}

async function onRun(func: MacroFunction) {
  runningFunc.value = func.name;
  try {
    await replStore.ensureConnected();
    const callStr = buildPythonCall(func);
    replStore.executeCode(callStr);
  } catch (e) {
    console.error('Failed to run macro:', e);
  } finally {
    // Brief loading state
    setTimeout(() => {
      runningFunc.value = null;
    }, 500);
  }
}

function onDragStart(e: DragEvent, func: MacroFunction) {
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'copy';
    e.dataTransfer.setData(
      'application/json',
      JSON.stringify({
        type: 'macro',
        fileName: props.filename,
        itemName: func.name,
        deviceId: '',
      }),
    );
  }
}
</script>

<style scoped>
.macro-panel {
  margin-bottom: 12px;
}

.macro-header {
  min-height: 44px;
  padding: 6px 12px;
}

:deep(.q-expansion-item__toggle-icon) {
  color: white;
}

.macro-content {
  background: white;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
}
</style>
