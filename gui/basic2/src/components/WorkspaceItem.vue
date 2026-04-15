<template>
  <q-card flat bordered class="workspace-item">
    <q-card-section class="q-pa-sm">
      <!-- Header row: drag handle, device/item info, remove button -->
      <div class="row items-center no-wrap q-mb-xs">
        <q-icon name="drag_indicator" class="drag-handle q-mr-xs" color="grey-5" size="sm" />
        <q-icon
          :name="itemIcon"
          :color="itemColor"
          size="xs"
          class="q-mr-xs"
        />
        <span v-if="item.type !== 'macro'" class="text-caption text-grey-6 q-mr-xs">{{ item.deviceId }} /</span>
        <span v-else class="text-caption text-grey-6 q-mr-xs">{{ item.fileName }} /</span>
        <span class="text-weight-medium text-body2">{{ item.itemName }}</span>
        <q-space />
        <q-btn flat dense round size="sm" icon="close" color="grey" @click="emit('remove')">
          <q-tooltip>Remove from shelf</q-tooltip>
        </q-btn>
      </div>

      <!-- Property value display and edit -->
      <div v-if="item.type === 'property' && propertySpec">
        <div class="row items-center no-wrap q-gutter-sm property-row">
          <div class="col-6">
            <code class="current-value">{{
              formatValue(deviceState[item.itemName], propertySpec.unit)
            }}</code>
          </div>
          <div v-if="!propertySpec.read_only" class="col-6">
            <PropertyInput
              :property="propertySpec"
              :value="deviceState[item.itemName]"
              class="property-input-large"
              @update="(val) => onUpdateProperty(val)"
            />
          </div>
        </div>
      </div>

      <!-- Command execution -->
      <div v-if="item.type === 'command' && commandSpec">
        <div class="row items-center q-gutter-sm">
          <q-btn
            unelevated
            no-caps
            color="light-blue-10"
            label="Run"
            padding="4px 16px"
            :loading="running"
            @click="onRunCommand"
          />
          <div v-if="hasCommandArgs" class="col">
            <q-btn
              flat
              dense
              size="sm"
              :icon="showArgs ? 'expand_less' : 'expand_more'"
              :label="showArgs ? 'Hide' : 'Args'"
              @click="showArgs = !showArgs"
            />
          </div>
        </div>

        <!-- Arguments -->
        <div v-if="showArgs && hasCommandArgs" class="q-mt-xs">
          <div v-for="arg in commandSpec.args" :key="arg.name" class="row items-center q-mb-xs">
            <div class="col-3 text-caption">{{ arg.name }}</div>
            <div class="col-9">
              <ArgInput
                :arg="arg"
                :value="argValues[arg.name]"
                class="arg-input-large"
                @update="(v) => (argValues[arg.name] = v)"
              />
            </div>
          </div>
        </div>

        <!-- Result -->
        <div v-if="cmdResult !== null" class="q-mt-xs">
          <pre class="result-box">{{ formatResult(cmdResult) }}</pre>
        </div>
        <div v-if="cmdError" class="q-mt-xs">
          <pre class="error-box">{{ cmdError }}</pre>
        </div>
      </div>

      <!-- Macro execution -->
      <div v-if="item.type === 'macro' && macroSpec">
        <div class="row items-center q-gutter-sm">
          <q-btn
            unelevated
            no-caps
            color="pink-9"
            label="Run"
            padding="4px 16px"
            :loading="running"
            @click="onRunMacro"
          />
          <div v-if="hasMacroArgs" class="col">
            <q-btn
              flat
              dense
              size="sm"
              :icon="showArgs ? 'expand_less' : 'expand_more'"
              :label="showArgs ? 'Hide' : 'Args'"
              @click="showArgs = !showArgs"
            />
          </div>
        </div>

        <!-- Arguments -->
        <div v-if="showArgs && hasMacroArgs" class="q-mt-xs">
          <div
            v-for="arg in macroSpec.func.args"
            :key="arg.name"
            class="row items-center q-mb-xs"
          >
            <div class="col-3 text-caption">{{ arg.name }}</div>
            <div class="col-9">
              <ArgInput
                :arg="toCommandArg(arg)"
                :value="argValues[arg.name]"
                class="arg-input-large"
                @update="(v) => (argValues[arg.name] = v)"
              />
            </div>
          </div>
        </div>
      </div>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue';
import { useDevicesStore } from 'stores/devices';
import { useMacrosStore, type MacroArg } from 'stores/macros';
import { useReplStore } from 'stores/repl';
import type { WorkspaceItem } from 'stores/workspace';
import type { CommandArg } from 'src/api/devices';
import { formatValue } from 'src/utils/formatter';
import PropertyInput from './PropertyInput.vue';
import ArgInput from './ArgInput.vue';

const props = defineProps<{
  item: WorkspaceItem;
  index: number;
}>();

const emit = defineEmits<{
  remove: [];
}>();

const store = useDevicesStore();
const macrosStore = useMacrosStore();
const replStore = useReplStore();

const deviceState = computed(() => store.getStateForPath(props.item.deviceId));
const propertySpec = computed(() =>
  store.getPropertySpec(props.item.deviceId, props.item.itemName),
);
const commandSpec = computed(() => store.getCommandSpec(props.item.deviceId, props.item.itemName));
const macroSpec = computed(() =>
  props.item.fileName
    ? macrosStore.getMacroFunction(props.item.fileName, props.item.itemName)
    : null,
);

const itemIcon = computed(() => {
  switch (props.item.type) {
    case 'property': return 'tune';
    case 'command': return 'bolt';
    case 'macro': return 'functions';
    default: return 'help';
  }
});

const itemColor = computed(() => {
  switch (props.item.type) {
    case 'property': return 'primary';
    case 'command': return 'orange';
    case 'macro': return 'pink-9';
    default: return 'grey';
  }
});

// Shared state
const showArgs = ref(false);
const running = ref(false);
const argValues = reactive<Record<string, unknown>>({});
const cmdResult = ref<unknown>(null);
const cmdError = ref<string | null>(null);

const hasCommandArgs = computed(
  () => Array.isArray(commandSpec.value?.args) && commandSpec.value.args.length > 0,
);

const hasMacroArgs = computed(
  () => (macroSpec.value?.func.args.length || 0) > 0,
);

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

async function onUpdateProperty(value: unknown) {
  try {
    await store.updateProperty(props.item.deviceId, props.item.itemName, value);
  } catch (e) {
    console.error('Failed to update property:', e);
  }
}

async function onRunCommand() {
  if (!commandSpec.value) return;

  running.value = true;
  cmdResult.value = null;
  cmdError.value = null;

  try {
    const args = buildCommandArgs();
    cmdResult.value = await store.runCommand(props.item.deviceId, props.item.itemName, args);
  } catch (e) {
    cmdError.value = e instanceof Error ? e.message : String(e);
  } finally {
    running.value = false;
  }
}

async function onRunMacro() {
  if (!macroSpec.value) return;

  running.value = true;
  try {
    await replStore.ensureConnected();
    const callStr = buildMacroPythonCall();
    replStore.executeCode(callStr);
  } catch (e) {
    console.error('Failed to run macro:', e);
  } finally {
    setTimeout(() => {
      running.value = false;
    }, 500);
  }
}

function buildCommandArgs(): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const arg of commandSpec.value?.args || []) {
    const val = argValues[arg.name];
    result[arg.name] = coerceArg(arg, val);
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

function formatPythonValue(arg: MacroArg, value: unknown): string {
  if (value === null || value === undefined || value === '') {
    if (!arg.required && arg.default !== undefined) return '';
    return 'None';
  }
  const t = arg.type?.toLowerCase() || '';
  if (t === 'bool') return value ? 'True' : 'False';
  if (t === 'int' || t === 'float') return String(value as number);
  const s = String(value as string | number);
  return `'${s.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;
}

function buildMacroPythonCall(): string {
  if (!macroSpec.value) return '';
  const func = macroSpec.value.func;
  const args: string[] = [];
  for (const arg of func.args) {
    const val = argValues[arg.name];
    if (val === undefined || val === null || val === '') {
      if (!arg.required) continue;
    }
    const pyVal = formatPythonValue(arg, val);
    if (pyVal === '') continue;
    args.push(`${arg.name}=${pyVal}`);
  }
  return `${func.name}(${args.join(', ')})`;
}

function formatResult(r: unknown): string {
  try {
    return JSON.stringify(r, null, 2);
  } catch {
    return String(r);
  }
}
</script>

<style scoped>
.workspace-item {
  background: #fafafa;
  cursor: grab;
}

.workspace-item:active {
  cursor: grabbing;
}

.drag-handle {
  cursor: grab;
}

.current-value {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  background: #f0f0f0;
  padding: 6px 10px;
  border-radius: 4px;
  display: block;
  text-align: center;
}

.property-input-large {
  width: 100%;
}

.property-input-large :deep(.q-field__control) {
  min-height: 36px;
}

.arg-input-large {
  width: 100%;
}

.arg-input-large :deep(.q-field__control) {
  min-height: 32px;
}

.result-box {
  background: #f5f5f5;
  border: 1px solid #eee;
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 11px;
  max-height: 80px;
  overflow: auto;
  margin: 0;
}

.error-box {
  background: #fff5f5;
  border: 1px solid #fdd;
  border-radius: 4px;
  padding: 4px 8px;
  color: #c00;
  font-size: 11px;
  margin: 0;
}
</style>
