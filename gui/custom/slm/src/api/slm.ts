// src/api/slm.ts
// Typed REST/WebSocket helper for the SLM device.

//
// ─── Types ───────────────────────────────────────────────────────────────────
//

export interface TrapState {
  x: number
  y: number
  z: number
  beam_type: string
  aperture_diameter: number
  bessel_inner_fraction: number
  offset_h: number
  offset_v: number
  width: number
  height: number
  auto_update: boolean
}

export interface MaskState {
  vertical_show: boolean
  vertical_idx: number
  vertical_size: number
  horizontal_show: boolean
  horizontal_idx: number
  horizontal_size: number
}

export interface SlmRootState {
  max_phase: number
  phase_offset: number
  monitor_name: string | null
  trap: TrapState
  mask: MaskState
  [key: string]: unknown
}

export interface SlmDevice {
  id: string
  kind: string
  status: string
  locked_by: string | null
  state: SlmRootState
}

//
// ─── HTTP Helpers ─────────────────────────────────────────────────────────────
//

const apiBase = '/api/v2'

function api(path: string) {
  return `${apiBase}${path}`
}

async function parseJSON<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`)
  return (await r.json()) as T
}

export async function getSlm(signal?: AbortSignal): Promise<SlmDevice> {
  const init: RequestInit = signal ? { signal } : {}
  const r = await fetch(api('/devices/slm'), init)
  return parseJSON<SlmDevice>(r)
}

export async function patchTrapProperties(properties: Partial<TrapState>): Promise<unknown> {
  const r = await fetch(api('/devices/slm/trap'), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ properties }),
  })
  if (!r.ok) throw new Error(`PATCH trap failed: HTTP ${r.status}`)
  return r.json()
}

export async function patchMaskProperties(properties: Partial<MaskState>): Promise<unknown> {
  const r = await fetch(api('/devices/slm/mask'), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ properties }),
  })
  if (!r.ok) throw new Error(`PATCH mask failed: HTTP ${r.status}`)
  return r.json()
}

export async function sendTrapCommand(name: string, args: Record<string, unknown> = {}): Promise<unknown> {
  const r = await fetch(api('/devices/slm/trap/commands'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, args }),
  })
  if (!r.ok) throw new Error(`command ${name} failed: HTTP ${r.status}`)
  return r.json()
}

//
// ─── WebSocket ────────────────────────────────────────────────────────────────
//

export function openEventsSocket(devId: string = 'slm'): WebSocket {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${location.host}/api/v2/events?ids=${devId}`
  return new WebSocket(url)
}

// Fetches the most-recent frame for a data source via REST.
// Returns the base64-encoded PNG string, or null on failure.
export async function getImageFrame(devicePath: string, source: string): Promise<string | null> {
  try {
    const r = await fetch(api(`/devices/${devicePath}/data/${source}/frame`))
    if (!r.ok) return null
    const data = (await r.json()) as { image_b64?: string }
    return data.image_b64 ?? null
  } catch {
    return null
  }
}

// Opens a WebSocket image stream.
// devicePath: 'slm' for root sources, 'slm/trap' for child sources.
// source: data source name, e.g. 'current_pattern', 'trap_pattern'.
// Messages: JSON { image_b64: string }
export function openImageStream(devicePath: string, source: string, rate = 5): WebSocket {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const qs = new URLSearchParams({ rate: String(rate) })
  const url = `${proto}://${location.host}/api/v2/streams/${devicePath}/${source}?${qs}`
  return new WebSocket(url)
}
