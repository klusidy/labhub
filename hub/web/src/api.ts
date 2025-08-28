// Tiny REST + WS helpers that tolerate missing endpoints.
export type Device = { id: string; kind: string; status: string; state: any };

const base = ''; // same origin (served by FastAPI at /ui)
const api = (p: string) => `${base}/api/v1${p}`;

export async function listDevices(): Promise<Device[]> {
  const r = await fetch(api('/devices')); if (!r.ok) throw new Error('devices');
  return r.json();
}
export async function getSpec(id: string): Promise<any|null> {
  const r = await fetch(api(`/devices/${id}/spec`));
  if (r.status === 404) return null; // spec not implemented yet
  if (!r.ok) throw new Error('spec ${r.status}'); return r.json();
}
export async function patchProperties(id: string, properties: Record<string, any>) {
  const r = await fetch(api(`/devices/${id}`), {
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ properties })
  });
  if (!r.ok){
    // Try to surface FastAPI’s error details
    let detail = '';
    try {
      const data = await r.json();
      detail = JSON.stringify(data);
    } catch {
      detail = await r.text();
    }
    throw new Error(`PATCH /devices/${id} ${r.status} ${r.statusText} – ${detail}`);
  }
  
  return r.json();
}
export async function runCommand(id: string, name: string, args: Record<string, any> = {}) {
  const r = await fetch(api(`/devices/${id}/commands`), {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ name, args }),
  });
  if (!r.ok) throw new Error('command'); 
  //return r.json().catch(()=> ({}));
  return await r.json();
}

export function openEvents(ids: string[] = [], rate?: number): WebSocket {
  // if server supports ids/rate query, include it; otherwise hub ignores it
  const qs = new URLSearchParams();
  if (ids.length) qs.set('ids', ids.join(','));
  if (rate) qs.set('rate', String(rate));
  const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/v1/events?${qs}`;
  const ws = new WebSocket(url);
  return ws;
}

// Optional binary stream WS (JSON fallback)
export function openDataStream(id: string, source:string, rate?: number, format: 'json'|'msgpack'='json'): WebSocket {
  const qs = new URLSearchParams();
  if (rate) qs.set('rate', String(rate));
  qs.set('format', format);
  const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/v1/streams/${id}/${source}?${qs}`;
  const ws = new WebSocket(url);
  if (format === 'msgpack') ws.binaryType = 'arraybuffer';
  return ws;
}


export async function getPlotSpec(id: string, source: string) {
  const r = await fetch(api(`/devices/${id}/data/${source}/plot`));
  if (!r.ok) throw new Error(`plot spec ${r.status}`);
  return r.json();
}

export async function getFrame(id: string, source: string) {
  const r = await fetch(api(`/devices/${id}/data/${source}/frame`));
  if (!r.ok) throw new Error(`frame ${r.status}`);
  return r.json(); // { data: number[] }
}

export async function startSource(id: string, source: string) {
  const r = await fetch(api(`/devices/${id}/data/${source}/start`), { method: "POST" });
  if (!r.ok) throw new Error(`start ${r.status}`);
}

export async function stopSource(id: string, source: string) {
  const r = await fetch(api(`/devices/${id}/data/${source}/stop`), { method: "POST" });
  if (!r.ok) throw new Error(`stop ${r.status}`);
}