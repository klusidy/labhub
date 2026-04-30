import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from 'src/api/chameleon'

export interface PinnedVariable {
  id: string
  nodeId: string
  nodeLabel: string
  moduleType: string
  propKey: string
  propLabel: string
  unit?: string
}

const SHELF_KEY = 'chameleon:shelf'

export const useChameleonStore = defineStore('chameleon', () => {
  const connected = ref(false)
  const spec = ref<api.ChameleonSpec | null>(null)
  const deviceState = ref<api.ChameleonDevice | null>(null)
  const pinnedVars = ref<PinnedVariable[]>(loadShelf())
  let ws: WebSocket | null = null

  const moduleState = computed(
    () => (moduleId: string): Record<string, unknown> =>
      (deviceState.value?.state[moduleId] as Record<string, unknown>) ?? {},
  )

  function loadShelf(): PinnedVariable[] {
    try {
      const raw = localStorage.getItem(SHELF_KEY)
      return raw ? (JSON.parse(raw) as PinnedVariable[]) : []
    } catch {
      return []
    }
  }

  function saveShelf() {
    localStorage.setItem(SHELF_KEY, JSON.stringify(pinnedVars.value))
  }

  async function init() {
    try {
      ;[spec.value, deviceState.value] = await Promise.all([api.fetchSpec(), api.fetchDevice()])
    } catch (e) {
      console.warn('Chameleon backend unavailable:', e)
    }
    ws?.close()
    ws = api.openEventsSocket((data) => {
      if (data && typeof data === 'object' && 'state' in data) {
        deviceState.value = data as api.ChameleonDevice
      }
      connected.value = true
    })
    ws.onclose = () => {
      connected.value = false
    }
  }

  async function patchModule(moduleId: string, patch: Record<string, unknown>) {
    await api.patchModule(moduleId, patch)
    if (deviceState.value?.state[moduleId]) {
      Object.assign(deviceState.value.state[moduleId] as object, patch)
    }
  }

  function pinVariable(pin: Omit<PinnedVariable, 'id'>) {
    const id = `${pin.nodeId}:${pin.propKey}`
    if (!pinnedVars.value.find((p) => p.id === id)) {
      pinnedVars.value.push({ ...pin, id })
      saveShelf()
    }
  }

  function unpinVariable(id: string) {
    pinnedVars.value = pinnedVars.value.filter((p) => p.id !== id)
    saveShelf()
  }

  function getPinnedValue(pin: PinnedVariable): unknown {
    const state = moduleState.value(pin.moduleType) ?? moduleState.value(pin.nodeId)
    return (state as Record<string, unknown>)[pin.propKey]
  }

  return {
    connected,
    spec,
    deviceState,
    pinnedVars,
    moduleState,
    init,
    patchModule,
    pinVariable,
    unpinVariable,
    getPinnedValue,
  }
})
