<template>
  <div class="device-config-panel">
    <!-- Header -->
    <div class="row items-center q-mb-md">
      <q-icon name="link_off" color="grey-5" size="md" class="q-mr-sm" />
      <div>
        <div class="text-h5">{{ deviceConfig.id }}</div>
        <div class="text-caption text-grey-6">{{ deviceConfig.driver }}</div>
      </div>
      <q-btn
        flat
        dense
        round
        size="sm"
        icon="link"
        color="positive"
        class="q-ml-sm"
        @click="$emit('connect', deviceConfig.id)"
      >
        <q-tooltip>Connect</q-tooltip>
      </q-btn>
    </div>

    <!-- Device ID (read-only) -->
    <q-input
      :model-value="deviceConfig.id"
      label="Device ID"
      outlined
      dense
      disable
      class="q-mb-md"
    />

    <!-- Driver (read-only) -->
    <q-input
      :model-value="deviceConfig.driver"
      label="Driver"
      outlined
      dense
      disable
      class="q-mb-md"
    />

    <!-- YAML options editor -->
    <div class="text-subtitle2 q-mb-xs">Options (YAML)</div>
    <q-input
      v-model="optionsYaml"
      type="textarea"
      outlined
      dense
      :rows="10"
      class="config-textarea q-mb-md"
      hint="Device-specific options in YAML format"
      :error="!!yamlError"
      :error-message="yamlError ?? undefined"
      @update:model-value="onYamlChange"
    />

    <!-- Action buttons -->
    <div class="row q-gutter-sm">
      <q-btn color="primary" icon="save" label="Save" :loading="saving" @click="onSave" />
      <q-btn
        color="positive"
        icon="link"
        label="Connect"
        :loading="connecting"
        @click="$emit('connect', deviceConfig.id)"
      >
        <q-tooltip>Connect device</q-tooltip>
      </q-btn>
      <q-space />
      <q-btn
        color="negative"
        icon="delete"
        label="Remove"
        @click="$emit('remove', deviceConfig.id)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import yaml from 'js-yaml';
import type { DeviceConfig } from '../api/admin';

const props = defineProps<{
  deviceConfig: DeviceConfig;
}>();

const emit = defineEmits<{
  (e: 'save', devId: string, config: DeviceConfig): void;
  (e: 'connect', devId: string): void;
  (e: 'remove', devId: string): void;
}>();

const optionsYaml = ref('');
const yamlError = ref<string | null>(null);
const saving = ref(false);
const connecting = ref(false);

function deviceToYaml(config: DeviceConfig): string {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { id, driver, should_connect, ...options } = config;
  if (Object.keys(options).length === 0) return '';
  try {
    return yaml.dump(options, { indent: 2, lineWidth: -1 });
  } catch {
    return '';
  }
}

function yamlToOptions(yamlStr: string): Record<string, unknown> {
  if (!yamlStr.trim()) return {};
  return (yaml.load(yamlStr) as Record<string, unknown>) || {};
}

function updateFromProps() {
  optionsYaml.value = deviceToYaml(props.deviceConfig);
  yamlError.value = null;
}

function onYamlChange() {
  try {
    yamlToOptions(optionsYaml.value);
    yamlError.value = null;
  } catch (e) {
    yamlError.value = e instanceof Error ? e.message : 'Invalid YAML';
  }
}

function onSave() {
  try {
    const options = yamlToOptions(optionsYaml.value);
    const config: DeviceConfig = {
      id: props.deviceConfig.id,
      driver: props.deviceConfig.driver,
      ...options,
    };
    emit('save', props.deviceConfig.id, config);
  } catch (e) {
    yamlError.value = e instanceof Error ? e.message : 'Invalid YAML';
  }
}

watch(() => props.deviceConfig, updateFromProps, { immediate: true, deep: true });
</script>

<style scoped>
.device-config-panel {
  max-width: 700px;
}

.config-textarea :deep(textarea) {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}
</style>
