// src/stores/picoscope.ts

import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  getPicoscope,
  getPicoscopeSpec,
  getPicoscopePlotSpec,
  patchPicoscopeProperties,
  sendPicoscopeCommand,
  openEventsSocket,
  type PicoscopeDevice,
  type PicoscopeSpec,
  type PlotSpec,
  type PicoscopePropertiesPatch,
  type SetChannelArgs,
  type SetSimpleTriggerArgs,
  type AcquireToFileArgs,
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
  const channels = () => device.value?.state?._channel_settings
  const trigger = () => device.value?.state?._trigger_settings

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

  /** set_channel command */
  async function setChannel(args: SetChannelArgs) {
    try {
      await sendPicoscopeCommand('set_channel', args)
      await refresh()
    } catch (e) {
      console.error('setChannel failed:', e)
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
    trigger,

    // actions
    init,
    refresh,
    patchProps,
    setChannel,
    setTriggerSimple,
    acquireToFile,
    fetchPlotSpec,
  }
})
