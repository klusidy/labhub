// src/api/picoscope.ts
// Typed REST/WebSocket helper for PicoScope.

//
// ─────────────────────────────────────────────────────────────────────────────
//  Types for state
// ─────────────────────────────────────────────────────────────────────────────
//

export type ChannelId = 'A' | 'B' | 'C' | 'D'

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

export const ChannelIndex: Record<ChannelId, number> = {
  A: 0,
  B: 1,
  C: 2,
  D: 3,
}

export const ChannelIdFromIndex = (i: number): ChannelId =>
  (['A', 'B', 'C', 'D'] as ChannelId[])[i] ?? 'A'

export interface ChannelSettings {
  status: number
  channel: number
  enable: 0 | 1
  coupling_type: number
  range: number
  multiplier: number
  range_str: Range
  coupling_type_str: 'AC' | 'DC'
}

export interface TriggerSettingsRaw {
  status: number
  enable: 0 | 1
  source: number
  source_str: string
  threshold: number
  threshold_mV: number
  direction: number
  direction_str: string
  delay: number
  auto_trigger_ms: number
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

  _channel_settings: Record<ChannelId, ChannelSettings>
  _trigger_settings: TriggerSettingsRaw

  [key: string]: unknown
}

export interface PicoscopeDevice {
  id: 'picoscope'
  kind: string
  status: string
  locked_by: string | null
  state: PicoscopeState
}

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
}

//
// ─────────────────────────────────────────────────────────────────────────────
//  HTTP Helpers
// ─────────────────────────────────────────────────────────────────────────────
//

const apiBase = '/api/v1'

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

//
// ─────────────────────────────────────────────────────────────────────────────
//  Commands (POST /api/v1/devices/picoscope/commands)
// ─────────────────────────────────────────────────────────────────────────────
//

export interface SetChannelArgs {
  channel: ChannelId
  enable: boolean
  coupling_type: 'AC' | 'DC'
  range: '10MV' | '20MV' | '50MV' | '100MV' | '200MV' | '500MV' | '1V' | '2V' | '5V' | '10V' | '20V' // | '50V' | 'MAX_RANGES';
}

export type TriggerDirection = 'RISING' | 'FALLING' | 'RISING_OR_FALLING'

export interface SetSimpleTriggerArgs {
  enable: boolean
  source: ChannelId
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

export type PicoscopeCommandName = 'set_channel' | 'set_simple_trigger' | 'acquire_to_file'

export interface CommandArgsMap {
  set_channel: SetChannelArgs
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
  const url = `${proto}://${location.host}/api/v1/events?ids=${dev_id}`
  return new WebSocket(url)
}

/// ───────────────────────────────────────────
// stuff for data streams
/// ───────────────────────────────────────────
export async function getFrame(dev_id: string = 'picoscope', source: string) {
  const r = await fetch(api(`/devices/${dev_id}/data/${source}/frame`))
  if (!r.ok) throw new Error(`frame ${r.status}`)
  return r.json() // { data: number[] }
}
