<template>
  <VueFlow
    class="chameleon-flow"
    :default-edge-options="defaultEdgeOptions"
    :connection-line-style="{ stroke: 'rgba(255,255,255,0.4)', strokeWidth: 2 }"
    :node-types="nodeTypes"
    fit-view-on-init
    @node-click="onNodeClick"
    @pane-click="onPaneClick"
    @connect="onConnect"
    @nodes-change="onNodesChange"
    @edges-change="onEdgesChange"
  >
    <Background variant="dots" :gap="24" :size="1.2" pattern-color="#333" />
    <Controls :show-interactive="false" />
  </VueFlow>
</template>

<script setup lang="ts">
import { markRaw, onMounted } from 'vue'
import {
  VueFlow,
  useVueFlow,
  type Node,
  type Edge,
  type Connection,
  type NodeMouseEvent,
  type NodeChange,
  type EdgeChange,
} from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import AdcInputNode from 'components/nodes/AdcInputNode.vue'
import SigGenNode from 'components/nodes/SigGenNode.vue'
import OscilloscopeNode from 'components/nodes/OscilloscopeNode.vue'

export interface ModuleNodeData {
  label: string
  moduleType: string
  busOutputSlots: number[]
  inputCount: number
  inputLabels?: string[]
  outputLabels?: string[]
  config: Record<string, unknown>
  propSpecs?: Record<
    string,
    {
      label: string
      type: 'number' | 'bool' | 'choice'
      unit?: string
      choices?: string[]
      readonly?: boolean
      min?: number
      max?: number
    }
  >
}

const emit = defineEmits<{
  'node-selected': [node: Node<ModuleNodeData> | null]
}>()

// Node type registry - must be markRaw to avoid reactivity issues
const nodeTypes = markRaw({
  adcInput: AdcInputNode,
  sigGen: SigGenNode,
  oscilloscope: OscilloscopeNode,
})

const defaultEdgeOptions = {
  type: 'smoothstep',
  animated: true,
  style: { stroke: 'rgba(255,255,255,0.35)', strokeWidth: 2 },
}

const CANVAS_KEY = 'chameleon:canvas'

function defaultNodes(): Node<ModuleNodeData>[] {
  return [
    {
      id: 'adc_0',
      type: 'adcInput',
      position: { x: 30, y: 60 },
      data: {
        label: 'ADC Input',
        moduleType: 'adc_input',
        busOutputSlots: [0, 1],
        inputCount: 0,
        outputLabels: ['ch0', 'ch1'],
        config: {},
        propSpecs: {
          decimation: { label: 'Decimation', type: 'number', min: 1, max: 65535 },
          averaging: { label: 'Averaging', type: 'bool' },
        },
      },
    },
    {
      id: 'sig_gen_0',
      type: 'sigGen',
      position: { x: 30, y: 230 },
      data: {
        label: 'Sig Gen',
        moduleType: 'sig_gen',
        busOutputSlots: [2],
        inputCount: 0,
        outputLabels: ['out'],
        config: {},
        propSpecs: {
          frequency: { label: 'Frequency', type: 'number', unit: 'Hz', min: 0, max: 62500000 },
          amplitude: { label: 'Amplitude', type: 'number', unit: 'V', min: 0, max: 1 },
          waveform: {
            label: 'Waveform',
            type: 'choice',
            choices: ['sine', 'square', 'triangle', 'sawtooth'],
          },
          enabled: { label: 'Output enable', type: 'bool' },
        },
      },
    },
    {
      id: 'osc_0',
      type: 'oscilloscope',
      position: { x: 250, y: 120 },
      data: {
        label: 'Oscilloscope',
        moduleType: 'oscilloscope',
        busOutputSlots: [],
        inputCount: 4,
        inputLabels: ['in0', 'in1', 'in2', 'in3'],
        config: {},
        propSpecs: {
          n_samples: { label: 'Samples', type: 'number', min: 16, max: 16384 },
          trigger_level: { label: 'Trigger level', type: 'number', unit: 'LSB' },
          trigger_input: {
            label: 'Trigger input',
            type: 'choice',
            choices: ['in0', 'in1', 'in2', 'in3'],
          },
          trigger_edge: {
            label: 'Trigger edge',
            type: 'choice',
            choices: ['rising', 'falling', 'either'],
          },
          pretrigger: { label: 'Pre-trigger', type: 'number', unit: '%', min: 0, max: 100 },
        },
      },
    },
  ]
}

function defaultEdges(): Edge[] {
  return []
}

function loadCanvas(): { nodes: Node<ModuleNodeData>[]; edges: Edge[] } {
  try {
    const raw = localStorage.getItem(CANVAS_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as { nodes: Node<ModuleNodeData>[]; edges: Edge[] }
      if (parsed.nodes?.length) return parsed
    }
  } catch {
    // fall through to defaults
  }
  return { nodes: defaultNodes(), edges: defaultEdges() }
}

const { nodes, edges, addEdges, onConnect, applyNodeChanges, applyEdgeChanges, fitView } =
  useVueFlow({ ...loadCanvas() })

function saveCanvas() {
  localStorage.setItem(CANVAS_KEY, JSON.stringify({ nodes: nodes.value, edges: edges.value }))
}

function onNodesChange(changes: NodeChange[]) {
  applyNodeChanges(changes)
  saveCanvas()
}

function onEdgesChange(changes: EdgeChange[]) {
  applyEdgeChanges(changes)
  saveCanvas()
}

onConnect((connection: Connection) => {
  addEdges([
    {
      ...connection,
      type: 'smoothstep',
      animated: true,
      style: { stroke: 'rgba(255,255,255,0.35)', strokeWidth: 2 },
    },
  ])
  saveCanvas()
  // TODO: translate sourceHandle (bus slot) + targetHandle (mux input index)
  // → patchModule(targetNode.data.moduleType, { [`mux_in${muxIdx}`]: slotIdx })
})

function onNodeClick({ node }: NodeMouseEvent) {
  emit('node-selected', node as Node<ModuleNodeData>)
}

function onPaneClick() {
  emit('node-selected', null)
}

function resetLayout() {
  localStorage.removeItem(CANVAS_KEY)
  const fresh = loadCanvas() // will return defaults since we just cleared
  nodes.value = fresh.nodes
  edges.value = fresh.edges
  void fitView()
}

onMounted(() => {
  void fitView({ padding: 0.3 })
})

defineExpose({ resetLayout })
</script>

<style scoped>
.chameleon-flow {
  width: 100%;
  height: 100%;
  background: #1a1a1a;
}
</style>
