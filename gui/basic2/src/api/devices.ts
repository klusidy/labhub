// API client for device interactions

const API_BASE = '/api/v2';

// Types
export interface DeviceState {
  id: string;
  driver: string;
  status: 'connected' | 'disconnected' | 'unhealthy';
  state: Record<string, unknown>;
  doc?: string;
}

export interface PropertySpec {
  name: string;
  type?: 'int' | 'float' | 'bool' | 'str';
  read_only?: boolean;
  default?: unknown;
  choices?: unknown[];
  fields?: Record<string, PropertySpec>;
  doc?: string;
  unit?: string;
  min?: number;
  max?: number;
  step?: number;
}

export interface CommandArg {
  name: string;
  type?: 'int' | 'float' | 'bool' | 'str';
  doc?: string;
  required?: boolean;
  default?: unknown;
  choices?: unknown[];
}

export interface CommandSpec {
  name: string;
  args?: CommandArg[];
  events?: { release?: string };
  doc?: string;
}

export interface DataSourceSpec {
  name: string;
  doc?: string;
  has_plot?: boolean;
}

export interface DeviceSpec {
  properties?: PropertySpec[];
  commands?: CommandSpec[];
  data_sources?: DataSourceSpec[];
}

export interface PlotSpec {
  title?: string;
  'x-label'?: string;
  'y-label'?: string;
  'x-values'?: number[];
  channel_settings?: Record<string, {
    multiplier?: number;
    range_str?: string;
    coupling_type_str?: string;
  }>;
}

// REST API functions
export async function listDevices(): Promise<DeviceState[]> {
  const r = await fetch(`${API_BASE}/devices`);
  if (!r.ok) throw new Error(`Failed to list devices: ${r.status}`);
  return r.json();
}

export async function getDeviceSpec(id: string): Promise<DeviceSpec | null> {
  const r = await fetch(`${API_BASE}/devices/${encodeURIComponent(id)}/spec`);
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`Failed to get spec: ${r.status}`);
  return r.json();
}

export async function patchProperties(
  id: string,
  properties: Record<string, unknown>
): Promise<DeviceState> {
  const r = await fetch(`${API_BASE}/devices/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ properties }),
  });
  if (!r.ok) {
    let detail = '';
    try {
      const data = await r.json();
      detail = JSON.stringify(data);
    } catch {
      detail = await r.text();
    }
    throw new Error(`PATCH failed: ${r.status} ${r.statusText} - ${detail}`);
  }
  return r.json();
}

export async function runCommand(
  id: string,
  name: string,
  args: Record<string, unknown> = {}
): Promise<unknown> {
  const r = await fetch(`${API_BASE}/devices/${encodeURIComponent(id)}/commands`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, args }),
  });
  if (!r.ok) throw new Error(`Command failed: ${r.status}`);
  return r.json();
}

export async function getPlotSpec(id: string, source: string): Promise<PlotSpec> {
  const r = await fetch(
    `${API_BASE}/devices/${encodeURIComponent(id)}/data/${encodeURIComponent(source)}/plot`
  );
  if (!r.ok) throw new Error(`Failed to get plot spec: ${r.status}`);
  return r.json();
}

export async function getFrame(id: string, source: string): Promise<unknown> {
  const r = await fetch(
    `${API_BASE}/devices/${encodeURIComponent(id)}/data/${encodeURIComponent(source)}/frame`
  );
  if (!r.ok) throw new Error(`Failed to get frame: ${r.status}`);
  return r.json();
}

// Admin API functions
export async function disconnectDevice(id: string): Promise<{ status: string; devices: DeviceState[] }> {
  const r = await fetch(`${API_BASE}/admin/device/${encodeURIComponent(id)}/disconnect`, {
    method: 'POST',
  });
  if (!r.ok) throw new Error(`Failed to disconnect device: ${r.status}`);
  return r.json();
}

export async function connectDevice(id: string): Promise<{ status: string; devices: DeviceState[] }> {
  const r = await fetch(`${API_BASE}/admin/device/${encodeURIComponent(id)}/connect`, {
    method: 'POST',
  });
  if (!r.ok) throw new Error(`Failed to connect device: ${r.status}`);
  return r.json();
}

// WebSocket functions
export function openEventsWebSocket(ids: string[] = [], rate?: number): WebSocket {
  const qs = new URLSearchParams();
  if (ids.length) qs.set('ids', ids.join(','));
  if (rate) qs.set('rate', String(rate));
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${protocol}://${location.host}${API_BASE}/events?${qs}`;
  return new WebSocket(url);
}

export function openDataStream(
  id: string,
  source: string,
  rate?: number,
  format: 'json' | 'msgpack' = 'json'
): WebSocket {
  const qs = new URLSearchParams();
  if (rate) qs.set('rate', String(rate));
  qs.set('format', format);
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${protocol}://${location.host}${API_BASE}/streams/${encodeURIComponent(id)}/${encodeURIComponent(source)}?${qs}`;
  const ws = new WebSocket(url);
  if (format === 'msgpack') ws.binaryType = 'arraybuffer';
  return ws;
}
