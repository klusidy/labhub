<template>
  <!-- Choices (select) -->
  <q-select
    v-if="hasChoices"
    :model-value="currentValue"
    :options="selectOptions"
    :disable="disable"
    dense
    outlined
    emit-value
    map-options
    @update:model-value="(v) => emit('update', v)"
  />

  <!-- Boolean -->
  <q-toggle
    v-else-if="arg.type === 'bool'"
    :model-value="!!currentValue"
    :disable="disable"
    @update:model-value="(v) => emit('update', v)"
  />

  <!-- Number (int/float) -->
  <q-input
    v-else-if="isNumeric"
    :model-value="currentValue"
    type="number"
    :step="numStep"
    :disable="disable"
    dense
    outlined
    @update:model-value="(v) => emit('update', v)"
  />

  <!-- String (default) -->
  <q-input
    v-else
    :model-value="currentValue"
    :disable="disable"
    dense
    outlined
    @update:model-value="(v) => emit('update', v)"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { CommandArg } from 'src/api/devices';

const props = defineProps<{
  arg: CommandArg;
  value: unknown;
  disable?: boolean;
}>();

const emit = defineEmits<{
  update: [value: unknown];
}>();

// Initialize with default value if provided
const currentValue = computed<string | number | null>(() => {
  if (props.value !== undefined) {
    if (typeof props.value === 'boolean') return props.value ? 1 : 0;
    return props.value as string | number | null;
  }
  const def = props.arg.default ?? '';
  if (typeof def === 'boolean') return def ? 1 : 0;
  return def as string | number | null;
});

const hasChoices = computed(
  () => Array.isArray(props.arg.choices) && props.arg.choices.length > 0
);

const selectOptions = computed(() => {
  const opts = (props.arg.choices || []).map((c) => ({
    label: String(c),
    value: c,
  }));
  if (!props.arg.required) {
    opts.unshift({ label: '—', value: '' });
  }
  return opts;
});

const isNumeric = computed(
  () => props.arg.type === 'int' || props.arg.type === 'float'
);

const numStep = computed(() => {
  return props.arg.type === 'int' ? 1 : 'any';
});
</script>
