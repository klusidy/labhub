<template>
  <div class="detail-panel q-pa-sm">
    <!-- Header: label + close -->
    <div class="row items-center no-wrap q-mb-sm">
      <q-icon :name="typeIcon" size="16px" class="q-mr-xs" :style="{ color: typeColor }" />

      <!-- Editable label -->
      <q-input
        v-if="editingName"
        v-model="editedLabel"
        dense
        borderless
        autofocus
        class="col name-input"
        input-class="text-white text-caption text-weight-medium"
        @keyup.enter="commitRename"
        @keyup.escape="editingName = false"
        @blur="commitRename"
      />
      <span
        v-else
        class="col text-caption text-weight-medium text-white ellipsis cursor-pointer"
        style="font-size: 12px"
        @click="startRename"
      >
        {{ node.data.label }}
      </span>

      <q-btn flat round dense size="xs" icon="edit" color="grey-6" class="q-ml-xs" @click="startRename">
        <q-tooltip>Rename</q-tooltip>
      </q-btn>
      <q-btn flat round dense size="xs" icon="close" color="grey-6" @click="$emit('close')" />
    </div>

    <div class="text-caption text-grey-6 q-mb-sm" style="font-size: 10px">
      {{ node.data.moduleType }} · node {{ node.id }}
    </div>

    <q-separator dark class="q-mb-sm" />

    <!-- Property fields -->
    <div v-if="propSpecs && Object.keys(propSpecs).length" class="props-grid">
      <template v-for="(spec, key) in propSpecs" :key="key">
        <div class="prop-label text-grey-5 text-caption">{{ spec.label }}</div>
        <div class="prop-value row items-center no-wrap">
          <!-- Choice -->
          <q-select
            v-if="spec.type === 'choice'"
            v-model="localConfig[key]"
            :options="spec.choices"
            dense
            borderless
            dark
            emit-value
            class="col"
            popup-content-class="bg-grey-9"
            @update:model-value="onPropChange(key)"
          />
          <!-- Bool -->
          <q-toggle
            v-else-if="spec.type === 'bool'"
            v-model="localConfig[key]"
            dense
            color="primary"
            size="xs"
            @update:model-value="onPropChange(key)"
          />
          <!-- Number -->
          <q-input
            v-else
            v-model.number="localConfig[key]"
            type="number"
            dense
            borderless
            dark
            class="col"
            input-class="text-white text-caption"
            :min="spec.min"
            :max="spec.max"
            :suffix="spec.unit"
            :readonly="spec.readonly"
            debounce="400"
            @update:model-value="onPropChange(key)"
          />
          <!-- Pin button -->
          <q-btn
            flat
            round
            dense
            size="xs"
            icon="push_pin"
            :color="isPinned(key) ? 'primary' : 'grey-7'"
            @click="togglePin(key, spec)"
          >
            <q-tooltip>{{ isPinned(key) ? 'Unpin from workspace' : 'Pin to workspace' }}</q-tooltip>
          </q-btn>
        </div>
      </template>
    </div>

    <div v-else class="text-caption text-grey-7 q-mt-sm">
      No configurable properties.
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useChameleonStore } from 'stores/chameleon'
import type { Node } from '@vue-flow/core'
import type { ModuleNodeData } from 'components/CanvasPanel.vue'
import type { PinnedVariable } from 'stores/chameleon'

const props = defineProps<{
  node: Node<ModuleNodeData>
}>()

const emit = defineEmits<{
  close: []
  pin: [pin: Omit<PinnedVariable, 'id'>]
  patch: [moduleType: string, patch: Record<string, unknown>]
  rename: [id: string, label: string]
}>()

const cs = useChameleonStore()

const editingName = ref(false)
const editedLabel = ref(props.node.data.label)

const propSpecs = computed(() => props.node.data.propSpecs ?? null)

// Local copy of config for editing
const localConfig = ref<Record<string, unknown>>({ ...props.node.data.config })

watch(
  () => props.node.data.config,
  (cfg) => {
    localConfig.value = { ...cfg }
  },
)

watch(
  () => props.node.id,
  () => {
    editingName.value = false
    editedLabel.value = props.node.data.label
    localConfig.value = { ...props.node.data.config }
  },
)

const typeIcon = computed(() => {
  const t = props.node.data.moduleType
  if (t === 'adc_input') return 'input'
  if (t === 'sig_gen') return 'waves'
  if (t === 'oscilloscope') return 'show_chart'
  return 'extension'
})

const typeColor = computed(() => {
  const t = props.node.data.moduleType
  if (t === 'adc_input') return '#42a5f5'
  if (t === 'sig_gen') return '#ffa726'
  if (t === 'oscilloscope') return '#66bb6a'
  return '#aaa'
})

function startRename() {
  editedLabel.value = props.node.data.label
  editingName.value = true
}

function commitRename() {
  editingName.value = false
  const label = editedLabel.value.trim()
  if (label && label !== props.node.data.label) {
    // Update node data label directly (canvas panel reads this)
    props.node.data.label = label
    emit('rename', props.node.id, label)
  }
}

function onPropChange(key: string) {
  const patch = { [key]: localConfig.value[key] }
  props.node.data.config = { ...props.node.data.config, ...patch }
  emit('patch', props.node.data.moduleType, patch)
}

function isPinned(key: string): boolean {
  return cs.pinnedVars.some((p) => p.nodeId === props.node.id && p.propKey === key)
}

function togglePin(
  key: string,
  spec: { label: string; unit?: string },
) {
  const existing = cs.pinnedVars.find((p) => p.nodeId === props.node.id && p.propKey === key)
  if (existing) {
    cs.unpinVariable(existing.id)
  } else {
    cs.pinVariable({
      nodeId: props.node.id,
      nodeLabel: props.node.data.label,
      moduleType: props.node.data.moduleType,
      propKey: key,
      propLabel: spec.label,
      unit: spec.unit,
    })
  }
}
</script>

<style scoped>
.detail-panel {
  background: #222;
}

.name-input {
  font-size: 12px;
}

.props-grid {
  display: grid;
  grid-template-columns: 1fr 1.6fr;
  gap: 2px 8px;
  align-items: center;
}

.prop-label {
  font-size: 10px;
  padding: 3px 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.prop-value {
  min-width: 0;
}
</style>
