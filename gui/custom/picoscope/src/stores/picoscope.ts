// src/stores/picoscope.ts

import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  getPicoscope,
  getPicoscopeSpec,
  getPicoscopePlotSpec,
  patchPicoscopeProperties,
  patchChannelProperties,
  sendPicoscopeCommand,
  openEventsSocket,
  type PicoscopeDevice,
  type PicoscopeSpec,
  type PlotSpec,
  type PicoscopePropertiesPatch,
  type ChannelSettings,
  type SetSimpleTriggerArgs,
  type AcquireToFileArgs,
  type HwChannelId,
  ChannelIndex,
  ChannelIdFromIndex,
} from 'src/api/picoscope'

export const usePicoscopeStore = defineStore('picoscope', () => {
  //
  // ───────────────────────────────────────────
  // State
  // ───────────────────────────────────────────
  //

  const loading = ref(true)
  const connected = ref(false)

  const spec = ref<PicoscopeSpec | null>(null)
  const device = ref<PicoscopeDevice | null>(null)
  const plotSpecs = ref<Record<string, PlotSpec>>({})

  const ws = ref<WebSocket | null>(null)
  //const lastEvent = ref<any>(null)
  const lastEvent = ref<unknown>(null)

  //
  // ───────────────────────────────────────────
  // Getters (simple function getters are fine)
  // ───────────────────────────────────────────
  //

  const state = () => device.value?.state

  // Map child device states ch_a..ch_d → Record<HwChannelId, ChannelSettings>
  const channels = (): Record<HwChannelId, ChannelSettings> | undefined => {
    const st = device.value?.state
    if (!st?.ch_a) return undefined
    return {
      A: st.ch_a as ChannelSettings,
      B: st.ch_b as ChannelSettings,
      C: st.ch_c as ChannelSettings,
      D: st.ch_d as ChannelSettings,
    }
  }

  //
  // ───────────────────────────────────────────
  // Actions
  // ───────────────────────────────────────────
  //

  /** load spec + device + WS */
  async function init() {
    loading.value = true

    try {
      spec.value = await getPicoscopeSpec()
      device.value = await getPicoscope()
      connected.value = true

      const ds = spec.value?.data_sources ?? []
      await Promise.all(ds.filter((s) => s.has_plot).map((s) => fetchPlotSpec(s.name)))

      openWS() // TODO - make this configurable somehow? (so that it works with more picoscopes eventually)
    } catch (e) {
      console.error('Picoscope init failed:', e)
      connected.value = false
    } finally {
      loading.value = false
    }
  }

  /** GET fresh /devices/picoscope */
  async function refresh() {
    try {
      device.value = await getPicoscope()
    } catch (e) {
      console.warn('refresh failed:', e)
    }
  }

  async function fetchPlotSpec(name: string): Promise<PlotSpec> {
    //const cached = plotSpecs.value[name]
    //if (cached) return cached

    const spec = await getPicoscopePlotSpec(name)
    plotSpecs.value[name] = spec
    return spec
  }

  /** PATCH /devices/picoscope */
  async function patchProps(props: PicoscopePropertiesPatch) {
    try {
      device.value = await patchPicoscopeProperties(props)
    } catch (e) {
      console.error('patchProps failed:', e)
    }
  }

  /** PATCH channel child device properties (replaces set_channel command) */
  async function patchChannel(channel: HwChannelId, props: Partial<ChannelSettings>) {
    try {
      await patchChannelProperties(channel, props)
      await refresh()
    } catch (e) {
      console.error('patchChannel failed:', e)
    }
  }

  /** set_simple_trigger command */
  async function setTriggerSimple(args: SetSimpleTriggerArgs) {
    try {
      await sendPicoscopeCommand('set_simple_trigger', args)
      await refresh()
    } catch (e) {
      console.error('setTriggerSimple failed:', e)
    }
  }

  /** acquire_to_file command */
  async function acquireToFile(args: AcquireToFileArgs) {
    try {
      const r = await sendPicoscopeCommand('acquire_to_file', args)
      return r
    } catch (e) {
      console.error('acquireToFile failed:', e)
      const r = 'error (look in the consocle for details)'
      return r
    }
  }

  //
  // ───────────────────────────────────────────
  // WebSocket
  // ───────────────────────────────────────────
  //

  function openWS(dev_id: string = 'picoscope') {
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }

    const socket = openEventsSocket(dev_id)
    ws.value = socket

    socket.onopen = () => console.log('event WS opened')

    socket.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        lastEvent.value = msg
        console.log('WS msg:', msg) // temporary debug log

        // tolerate both shapes: { id: "picoscope", ... } or { device: "picoscope", ... }
        const id = msg.id ?? msg.device

        if (id === 'picoscope') {
          // if it looks like a full device object
          if (msg.state) {
            // full device update
            device.value = {
              id: 'picoscope',
              kind: msg.kind ?? device.value?.kind ?? '',
              status: msg.status ?? device.value?.status ?? '',
              locked_by: msg.locked_by ?? device.value?.locked_by ?? null,
              state: msg.state,
            }
          }
        }
      } catch (err) {
        console.warn('bad WS packet', err)
      }
    }

    socket.onerror = (e) => console.error('WS error', e)
    socket.onclose = () => console.warn('WS closed')
  }

  //
  // ───────────────────────────────────────────
  // Expose
  // ───────────────────────────────────────────
  //

  return {
    // state
    loading,
    connected,
    spec,
    device,
    ws,
    lastEvent,
    plotSpecs,

    // getters
    state,
    channels,

    // actions
    init,
    refresh,
    patchProps,
    patchChannel,
    setTriggerSimple,
    acquireToFile,
    fetchPlotSpec,
  }
})
