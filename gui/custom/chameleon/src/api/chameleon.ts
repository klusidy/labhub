// REST + WebSocket API helpers for the Chameleon labhub device

export type ModuleId = string

export interface PropertySpec {
  label: string
  type: 'number' | 'bool' | 'choice'
  unit?: string
  choices?: string[]
  readonly?: boolean
  min?: number
  max?: number
  step?: number
}

export interface ModuleSpec {
  id: ModuleId
  type: string
  bus_output_slots: number[]
  input_count: number
  properties: Record<string, PropertySpec>
}

export interface ChameleonSpec {
  bus_slots: number
  modules: ModuleSpec[]
  data_sources: string[]
}

export interface ChameleonDevice {
  id: string
  state: Record<ModuleId, Record<string, unknown>>
}

export interface PlotSpec {
  title: string
  x_label: string
  y_label: string
  x_values?: number[]
  channels?: string[]
}

const BASE = '/api/v2/devices/chameleon'

export async function fetchSpec(): Promise<ChameleonSpec> {
  const r = await fetch(`${BASE}/spec`)
  if (!r.ok) throw new Error(`spec fetch failed: ${r.status}`)
  return r.json() as Promise<ChameleonSpec>
}

export async function fetchDevice(): Promise<ChameleonDevice> {
  const r = await fetch(BASE)
  if (!r.ok) throw new Error(`device fetch failed: ${r.status}`)
  return r.json() as Promise<ChameleonDevice>
}

export async function patchModule(
  moduleId: ModuleId,
  patch: Record<string, unknown>,
): Promise<void> {
  const r = await fetch(`${BASE}/${moduleId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  if (!r.ok) throw new Error(`patch ${moduleId} failed: ${r.status}`)
}

export async function postCommand(
  command: string,
  args: Record<string, unknown> = {},
): Promise<unknown> {
  const r = await fetch(`${BASE}/commands`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command, args }),
  })
  if (!r.ok) throw new Error(`command ${command} failed: ${r.status}`)
  return r.json()
}

export async function fetchFrame(source: string): Promise<unknown> {
  const r = await fetch(`${BASE}/data/${source}/frame`)
  if (!r.ok) throw new Error(`frame fetch failed: ${r.status}`)
  return r.json()
}

export function openEventsSocket(onMessage: (data: unknown) => void): WebSocket {
  const url = `ws://${location.host}/api/v2/events?ids=chameleon`
  const ws = new WebSocket(url)
  ws.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data as string))
    } catch {
      // ignore malformed frames
    }
  }
  return ws
}

export function openDataStream(
  source: string,
  rate: number,
  onFrame: (data: unknown) => void,
): WebSocket {
  const url = `ws://${location.host}/api/v2/streams/chameleon/${source}?rate=${rate}&format=json`
  const ws = new WebSocket(url)
  ws.onmessage = (e) => {
    try {
      onFrame(JSON.parse(e.data as string))
    } catch {
      // ignore malformed frames
    }
  }
  return ws
}
