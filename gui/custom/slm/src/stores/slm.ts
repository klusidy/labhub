// src/stores/slm.ts

import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getSlm,
  patchTrapProperties,
  patchMaskProperties,
  sendTrapCommand,
  openEventsSocket,
  type SlmDevice,
  type TrapState,
  type MaskState,
} from 'src/api/slm'

export const useSlmStore = defineStore('slm', () => {
  //
  // ─── State ───────────────────────────────────────────────────────────────────
  //

  const loading = ref(true)
  const connected = ref(false)
  const device = ref<SlmDevice | null>(null)
  const ws = ref<WebSocket | null>(null)

  //
  // ─── Getters ─────────────────────────────────────────────────────────────────
  //

  const trapState = () => device.value?.state.trap ?? null
  const maskState = () => device.value?.state.mask ?? null

  //
  // ─── Actions ─────────────────────────────────────────────────────────────────
  //

  async function init() {
    loading.value = true
    try {
      device.value = await getSlm()
      connected.value = true
      openWS()
    } catch (e) {
      console.error('SLM init failed:', e)
      connected.value = false
    } finally {
      loading.value = false
    }
  }

  async function refresh() {
    try {
      device.value = await getSlm()
    } catch (e) {
      console.warn('SLM refresh failed:', e)
    }
  }

  async function patchTrap(props: Partial<TrapState>) {
    try {
      await patchTrapProperties(props)
      await refresh()
    } catch (e) {
      console.error('patchTrap failed:', e)
    }
  }

  async function patchMask(props: Partial<MaskState>) {
    try {
      await patchMaskProperties(props)
      await refresh()
    } catch (e) {
      console.error('patchMask failed:', e)
    }
  }

  async function triggerUpdate() {
    try {
      await sendTrapCommand('update')
    } catch (e) {
      console.error('triggerUpdate failed:', e)
    }
  }

  async function removeOverlay() {
    try {
      await sendTrapCommand('remove_overlay')
    } catch (e) {
      console.error('removeOverlay failed:', e)
    }
  }

  //
  // ─── WebSocket ───────────────────────────────────────────────────────────────
  //

  function openWS() {
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }

    const socket = openEventsSocket('slm')
    ws.value = socket

    socket.onopen = () => console.log('SLM event WS opened')

    socket.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string) as Record<string, unknown>
        const id = (msg.id ?? msg.device) as string | undefined

        if (id === 'slm' && msg.state) {
          device.value = {
            id: 'slm',
            kind: (msg.kind as string) ?? device.value?.kind ?? '',
            status: (msg.status as string) ?? device.value?.status ?? '',
            locked_by: (msg.locked_by as string | null) ?? device.value?.locked_by ?? null,
            state: msg.state as SlmDevice['state'],
          }
        }
      } catch (err) {
        console.warn('bad WS packet', err)
      }
    }

    socket.onerror = (e) => console.error('SLM WS error', e)
    socket.onclose = () => console.warn('SLM WS closed')
  }

  //
  // ─── Expose ──────────────────────────────────────────────────────────────────
  //

  return {
    loading,
    connected,
    device,
    ws,
    trapState,
    maskState,
    init,
    refresh,
    patchTrap,
    patchMask,
    triggerUpdate,
    removeOverlay,
  }
})
