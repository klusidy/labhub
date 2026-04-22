// src/api/picoscope.ts
// Typed REST/WebSocket helper for PicoScope.

//
// ─────────────────────────────────────────────────────────────────────────────
//  Types for state
// ─────────────────────────────────────────────────────────────────────────────
//

export type ChannelId = 'A' | 'B' | 'C' | 'D' | 'X' | 'Y'

export type Range =
  | '10MV'
  | '20MV'
  | '50MV'
  | '100MV'
  | '200MV'
  | '500MV'
  | '1V'
  | '2V'
  | '5V'
  | '10V'
  | '20V' //| '50V'

export type HwChannelId = 'A' | 'B' | 'C' | 'D'

export const ChannelIndex: Record<HwChannelId, number> = {
  A: 0,
  B: 1,
  C: 2,
  D: 3,
}

export const ChannelIdFromIndex = (i: number): HwChannelId =>
  (['A', 'B', 'C', 'D'] as HwChannelId[])[i] ?? 'A'

// Channel settings as exposed by pico_channel ChildDevice properties
export interface ChannelSettings {
  enable: boolean
  coupling: 'AC' | 'DC'
  range: Range
}

// Shape returned by PlotSpec.channel_settings (subset, for multiplier lookup)
export interface PlotChannelSettings {
  multiplier: number
  range_str: Range
  coupling_type_str: 'AC' | 'DC'
}

export interface PicoscopeState {
  sampling_frequency: number
  sampling_time_ns: number
  max_data_samples: number
  max_data_seconds: number
  pre_trigger_samples: number
  post_trigger_samples: number
  post_trigger_samples_seconds: number
  downsample_window: number

  // Child channel devices — nested state from pico_channel ChildDevices
  ch_a: ChannelSettings
  ch_b: ChannelSettings
  ch_c: ChannelSettings
  ch_d: ChannelSettings

  [key: string]: unknown
}

export interface PicoscopeDevice {
  id: 'picoscope'
  kind: string
  status: string
  locked_by: string | null
  state: PicoscopeState
}

// Regular data frame with channel data
export type DataFrameType = {
  source: string
  seq: number
  ts: number
  multiplier?: number
} & Partial<Record<ChannelId, number[]>> & { [key: string]: unknown }

// Plot metadata frame (sent on stream start/restart)
export type PlotMetadataFrame = {
  type: 'plot_metadata'
  plot: PlotSpec
}

// Union type for all possible frames
export type Frame = DataFrameType | PlotMetadataFrame

//
// ─────────────────────────────────────────────────────────────────────────────
//  Spec Types
// ─────────────────────────────────────────────────────────────────────────────
//

export interface PropertySpec {
  name: string
  doc: string | null
  read_only: boolean
  unit: string | null
  type: string //'int' | 'float' | 'str' | 'bool';
  min: number | null
  max: number | null
  choices: string[] | null
  fields: unknown
  default: unknown
  step: number | null
}

export interface CommandArgSpec {
  name: string
  type: string
  doc: string | null
  required: boolean
  default: unknown
  choices: string[] | null
}

export interface CommandSpec {
  name: string
  doc: string | null
  args: CommandArgSpec[]
  events: Record<string, unknown>
}

export interface DataSourceSpec {
  name: string
  doc: string | null
  has_plot: boolean
}

export interface PicoscopeSpec {
  id: 'picoscope'
  kind: string
  driver: string | null
  driver_version: string | null
  doc: string | null
  properties: PropertySpec[]
  commands: CommandSpec[]
  data_sources: DataSourceSpec[]
}

export interface PlotSpec {
  title: string
  'x-label': string
  'y-label': string
  'x-values': number[]
  channel_settings?: Record<HwChannelId, PlotChannelSettings>
}

//
// ─────────────────────────────────────────────────────────────────────────────
//  HTTP Helpers
// ─────────────────────────────────────────────────────────────────────────────
//

const apiBase = '/api/v2'

function api(path: string) {
  return `${apiBase}${path}`
}

async function parseJSON<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return (await r.json()) as T
}

// GET /devices/picoscope
export async function getPicoscope(signal?: AbortSignal): Promise<PicoscopeDevice> {
  const init: RequestInit = signal ? { signal } : {}
  const r = await fetch(api('/devices/picoscope'), init)
  return parseJSON<PicoscopeDevice>(r)
}

// GET /devices/picoscope/spec
export async function getPicoscopeSpec(signal?: AbortSignal): Promise<PicoscopeSpec> {
  const init: RequestInit = signal ? { signal } : {}
  const r = await fetch(api('/devices/picoscope/spec'), init)
  return parseJSON<PicoscopeSpec>(r)
}

// GET /devices/picoscope/data/{name}/plot
export async function getPicoscopePlotSpec(name: string): Promise<PlotSpec> {
  const r = await fetch(api(`/devices/picoscope/data/${name}/plot`))
  if (!r.ok) {
    throw new Error(`failed to fetch plot spec for ${name}: ${r.status}`)
  }
  return r.json()
}

// POST /devices/picoscope { properties: ... }
export type PicoscopePropertiesPatch = Partial<{
  sampling_frequency: number
  pre_trigger_samples: number
  post_trigger_samples: number
  downsample_window: number
}>

export async function patchPicoscopeProperties(
  properties: PicoscopePropertiesPatch
): Promise<PicoscopeDevice> {
  const r = await fetch(api('/devices/picoscope'), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ properties }),
  })
  return parseJSON<PicoscopeDevice>(r)
}

// PATCH channel child device — replaces the old set_channel command
export async function patchChannelProperties(
  channel: HwChannelId,
  properties: Partial<ChannelSettings>
): Promise<unknown> {
  const chKey = `ch_${channel.toLowerCase()}`
  const r = await fetch(api(`/devices/picoscope/${chKey}`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ properties }),
  })
  if (!r.ok) throw new Error(`patch channel ${channel} failed: HTTP ${r.status}`)
  return r.json()
}

//
// ─────────────────────────────────────────────────────────────────────────────
//  Commands (POST /api/v2/devices/picoscope/commands)
// ─────────────────────────────────────────────────────────────────────────────
//

export type TriggerDirection = 'RISING' | 'FALLING' | 'RISING_OR_FALLING'

export interface SetSimpleTriggerArgs {
  enable: boolean
  source: HwChannelId
  threshold_mV: number
  direction: TriggerDirection
  delay?: number
  auto_trigger_ms?: number
}

export interface AcquireToFileArgs {
  folder: string
  filename: string
  acquisition_duration_s: number | null
}

export type PicoscopeCommandName = 'set_simple_trigger' | 'acquire_to_file'

export interface CommandArgsMap {
  set_simple_trigger: SetSimpleTriggerArgs
  acquire_to_file: AcquireToFileArgs
}

export async function sendPicoscopeCommand<K extends PicoscopeCommandName>(
  name: K,
  args: CommandArgsMap[K]
): Promise<string> {
  const r = await fetch(api('/devices/picoscope/commands'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, args }),
  })

  if (!r.ok) throw new Error(`command ${name} failed ${r.status}`)
  return await r.json()
}

export async function restartPicoscope(): Promise<string> {
  const r = await fetch(api('/admin/reload/picoscope'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '',
  })
  if (!r.ok) throw new Error(`picoscope restart failed ${r.status}`)
  return await r.json()
}

// export async function runPicoscopeCommand(name: string, args: Record<string, any> = {}) {
//   const r = await fetch(api(`/devices/picoscope/commands`), {
//     method:'POST', headers:{'Content-Type':'application/json'},
//     body: JSON.stringify({ name, args }),
//   });
//   if (!r.ok) throw new Error('command');
//   //return r.json().catch(()=> ({}));
//   return await r.json();
// }

//
// ─────────────────────────────────────────────────────────────────────────────
//  WebSocket
// ─────────────────────────────────────────────────────────────────────────────
//

export function openEventsSocket(dev_id: string = 'picoscope'): WebSocket {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${location.host}/api/v2/events?ids=${dev_id}`
  return new WebSocket(url)
}

/// ───────────────────────────────────────────
// stuff for data streams
/// ───────────────────────────────────────────
export async function getFrame(source: string): Promise<Frame> {
  const dev_id = 'picoscope' // TODO - make into parameter
  const r = await fetch(api(`/devices/${dev_id}/data/${source}/frame`))
  if (!r.ok) throw new Error(`frame ${r.status}`)
  return r.json() // { data: number[] }
}

export function openDataStream(
  source: string,
  rate?: number,
  format: 'json' | 'msgpack' = 'json'
): WebSocket {
  const dev_id = 'picoscope' // TODO - make into parameter
  const qs = new URLSearchParams()
  if (rate) qs.set('rate', String(rate))
  qs.set('format', format)
  const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/v2/streams/${dev_id}/${source}?${qs}`
  const ws = new WebSocket(url)
  if (format === 'msgpack') ws.binaryType = 'arraybuffer'
  return ws
}
