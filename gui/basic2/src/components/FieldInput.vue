<template>
  <!-- Choices (select) -->
  <q-select
    v-if="hasChoices"
    :model-value="displayValue"
    :options="meta.choices"
    dense
    outlined
    @update:model-value="(v) => emit('update', v)"
  />

  <!-- Boolean -->
  <q-toggle
    v-else-if="meta.type === 'bool'"
    :model-value="!!value"
    @update:model-value="(v) => emit('update', v)"
  />

  <!-- Number (int/float) -->
  <q-input
    v-else-if="isNumeric"
    :model-value="displayValue"
    type="number"
    :step="numStep"
    :min="meta.min"
    :max="meta.max"
    dense
    outlined
    @update:model-value="(v) => emit('update', Number(v))"
  />

  <!-- String (default) -->
  <q-input
    v-else
    :model-value="displayValue"
    dense
    outlined
    @update:model-value="(v) => emit('update', v)"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue';

interface FieldMeta {
  type?: string;
  choices?: unknown[];
  min?: number;
  max?: number;
  step?: number;
  default?: unknown;
}

const props = defineProps<{
  meta: FieldMeta;
  value: unknown;
}>();

const emit = defineEmits<{
  update: [value: unknown];
}>();

const displayValue = computed<string | number | null>(() => {
  if (props.value === null || props.value === undefined) return null;
  if (typeof props.value === 'string' || typeof props.value === 'number') {
    return props.value;
  }
  if (typeof props.value === 'object') {
    return JSON.stringify(props.value);
  }
  return String(props.value as string | number | boolean);
});

const hasChoices = computed(
  () => Array.isArray(props.meta.choices) && props.meta.choices.length > 0
);

const isNumeric = computed(
  () =>
    props.meta.type === 'int' ||
    props.meta.type === 'float' ||
    props.meta.min != null ||
    props.meta.max != null
);

const numStep = computed(() => {
  if (props.meta.step != null) return props.meta.step;
  return props.meta.type === 'int' ? 1 : 'any';
});
</script>
