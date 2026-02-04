<template>
  <div class="property-input row items-center no-wrap q-gutter-xs">
    <!-- Composite type -->
    <template v-if="property.fields">
      <q-btn dense outline size="sm" icon="edit" @click="showDialog = true">
        Edit
        <q-tooltip>Edit composite value</q-tooltip>
      </q-btn>

      <q-dialog v-model="showDialog">
        <q-card style="min-width: 350px">
          <q-card-section>
            <div class="text-h6">{{ property.name }}</div>
          </q-card-section>
          <q-card-section class="q-pt-none">
            <div
              v-for="[fname, fmeta] in fieldEntries(property.fields)"
              :key="fname"
              class="q-mb-md"
            >
              <div class="text-caption text-grey-8 q-mb-xs">{{ fname }}</div>
              <FieldInput
                :meta="fmeta"
                :value="editValue[fname]"
                @update="(v) => (editValue[fname] = v)"
              />
            </div>
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Cancel" v-close-popup />
            <q-btn color="primary" label="Set" @click="onSetComposite" />
          </q-card-actions>
        </q-card>
      </q-dialog>
    </template>

    <!-- Choices (select) -->
    <template v-else-if="hasChoices">
      <q-select
        v-model="editValue"
        :options="property.choices"
        dense
        outlined
        style="min-width: 120px"
        @update:model-value="onSet"
      />
    </template>

    <!-- Boolean -->
    <template v-else-if="property.type === 'bool'">
      <q-toggle v-model="editValue" @update:model-value="onSet" />
    </template>

    <!-- Number (int/float) -->
    <template v-else-if="isNumeric">
      <q-input
        v-model.number="editValue"
        type="number"
        :step="numStep"
        :min="property.min"
        :max="property.max"
        dense
        outlined
        style="width: 120px"
        @keyup.enter="onSet"
      >
        <template #append>
          <q-btn dense flat icon="check" size="sm" @click="onSet" />
        </template>
      </q-input>
    </template>

    <!-- String (default) -->
    <template v-else>
      <q-input
        v-model="editValue"
        dense
        outlined
        style="min-width: 120px"
        @keyup.enter="onSet"
      >
        <template #append>
          <q-btn dense flat icon="check" size="sm" @click="onSet" />
        </template>
      </q-input>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import type { PropertySpec } from 'src/api/devices';
import FieldInput from './FieldInput.vue';

const props = defineProps<{
  property: PropertySpec;
  value: unknown;
}>();

const emit = defineEmits<{
  update: [value: unknown];
}>();

const showDialog = ref(false);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const editValue = ref<any>(null);

// Initialize edit value from current value
watch(
  () => props.value,
  (val) => {
    if (props.property.fields) {
      // Composite: clone object
      editValue.value = structuredClone(val || {});
    } else {
      editValue.value = val ?? props.property.default ?? null;
    }
  },
  { immediate: true }
);

const hasChoices = computed(
  () =>
    Array.isArray(props.property.choices) && props.property.choices.length > 0
);

const isNumeric = computed(
  () =>
    props.property.type === 'int' ||
    props.property.type === 'float' ||
    props.property.min != null ||
    props.property.max != null
);

const numStep = computed(() => {
  if (props.property.step != null) return props.property.step;
  return props.property.type === 'int' ? 1 : 'any';
});

function fieldEntries(
  fields: Record<string, PropertySpec> | undefined
): [string, PropertySpec][] {
  if (!fields) return [];
  if (Array.isArray(fields))
    return fields.map((n: string) => [n, {} as PropertySpec]);
  return Object.entries(fields);
}

function onSet() {
  emit('update', editValue.value);
}

function onSetComposite() {
  emit('update', editValue.value);
  showDialog.value = false;
}
</script>

<style scoped>
.property-input {
  min-width: 100px;
}
</style>
