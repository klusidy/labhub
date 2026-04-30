<template>
  <q-layout view="hHh LpR fFf">
    <!-- Header -->
    <q-header class="bg-grey-9">
      <q-toolbar>
        <q-btn flat round dense icon="account_tree" color="grey-4" @click="leftOpen = !leftOpen">
          <q-tooltip>Toggle router canvas</q-tooltip>
        </q-btn>

        <q-toolbar-title class="text-grey-3 text-subtitle1 q-ml-xs">
          Chameleon
        </q-toolbar-title>

        <q-chip
          :color="cs.connected ? 'positive' : 'grey-7'"
          text-color="white"
          size="sm"
          :icon="cs.connected ? 'wifi' : 'wifi_off'"
          class="q-ml-sm"
        >
          {{ cs.connected ? 'Connected' : 'Offline' }}
        </q-chip>

        <q-space />

        <q-btn flat round dense icon="tune" color="grey-4" @click="rightOpen = !rightOpen">
          <q-tooltip>Toggle workspace shelf</q-tooltip>
        </q-btn>
      </q-toolbar>
    </q-header>

    <!-- Left drawer: router canvas + module detail panel -->
    <q-drawer
      v-model="leftOpen"
      side="left"
      :width="440"
      :breakpoint="0"
      bordered
      class="bg-grey-10 column no-wrap"
      style="overflow: hidden"
    >
      <div class="drawer-section-title row items-center q-px-md q-py-xs">
        <q-icon name="device_hub" size="xs" class="q-mr-xs text-grey-5" />
        <span class="text-caption text-grey-5 text-uppercase letter-spacing-wide">Router</span>
        <q-space />
        <q-btn
          flat
          round
          dense
          size="xs"
          icon="restart_alt"
          color="grey-5"
          @click="resetCanvas"
        >
          <q-tooltip>Reset canvas layout</q-tooltip>
        </q-btn>
      </div>

      <!-- Vue Flow canvas fills remaining drawer height -->
      <div class="col" style="min-height: 0; position: relative">
        <CanvasPanel ref="canvasRef" @node-selected="onNodeSelected" />
      </div>

      <!-- Slide-up module detail panel -->
      <Transition name="detail-slide">
        <ModuleDetailPanel
          v-if="selectedNode"
          :node="selectedNode"
          class="detail-panel"
          @close="selectedNode = null"
          @pin="cs.pinVariable"
          @patch="onPatchModule"
        />
      </Transition>
    </q-drawer>

    <!-- Right drawer: workspace shelf -->
    <q-drawer
      v-model="rightOpen"
      side="right"
      :width="270"
      :breakpoint="0"
      bordered
      class="bg-grey-10 column no-wrap"
    >
      <div class="drawer-section-title row items-center q-px-md q-py-xs">
        <q-icon name="dashboard" size="xs" class="q-mr-xs text-grey-5" />
        <span class="text-caption text-grey-5 text-uppercase letter-spacing-wide">Workspace</span>
      </div>
      <WorkspaceShelf class="col" />
    </q-drawer>

    <!-- Central area: scope plots -->
    <q-page-container>
      <ScopeView />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useChameleonStore } from 'stores/chameleon'
import CanvasPanel from 'components/CanvasPanel.vue'
import ModuleDetailPanel from 'components/ModuleDetailPanel.vue'
import WorkspaceShelf from 'components/WorkspaceShelf.vue'
import ScopeView from 'components/ScopeView.vue'
import type { ModuleNodeData } from 'components/CanvasPanel.vue'
import type { Node } from '@vue-flow/core'

const cs = useChameleonStore()

const leftOpen = ref(true)
const rightOpen = ref(false)
const selectedNode = ref<Node<ModuleNodeData> | null>(null)
const canvasRef = ref<InstanceType<typeof CanvasPanel> | null>(null)

function onNodeSelected(node: Node<ModuleNodeData> | null) {
  selectedNode.value = node
}

async function onPatchModule(moduleType: string, patch: Record<string, unknown>) {
  try {
    await cs.patchModule(moduleType, patch)
  } catch (e) {
    console.error('Patch failed:', e)
  }
}

function resetCanvas() {
  canvasRef.value?.resetLayout()
}

onMounted(() => {
  void cs.init()
})
</script>

<style scoped>
.drawer-section-title {
  height: 32px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
  flex-shrink: 0;
}

.letter-spacing-wide {
  letter-spacing: 0.08em;
}

.detail-panel {
  flex-shrink: 0;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  max-height: 320px;
  overflow-y: auto;
}

.detail-slide-enter-active,
.detail-slide-leave-active {
  transition:
    max-height 0.25s ease,
    opacity 0.2s ease;
}

.detail-slide-enter-from,
.detail-slide-leave-to {
  max-height: 0;
  opacity: 0;
}

.detail-slide-enter-to,
.detail-slide-leave-from {
  max-height: 320px;
  opacity: 1;
}
</style>
