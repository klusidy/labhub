// Admin API client for config management

const API_BASE = '/api/v2';

// ===== Types =====

export interface DeviceConfig {
  id: string;
  driver: string;
  should_connect?: boolean;
  [key: string]: unknown;
}

export interface ConfigResponse {
  path: string;
  config: {
    devices: DeviceConfig[];
    influx?: Record<string, unknown>;
  };
  raw: string;
}

export interface DriverInfo {
  id: string;
  vendor: string;
  name: string;
  path: string;
}

// ===== API Functions =====

export async function getConfig(): Promise<ConfigResponse> {
  const r = await fetch(`${API_BASE}/admin/config`);
  if (!r.ok) throw new Error(`Failed to get config: ${r.status}`);
  return r.json();
}

export async function updateConfig(
  devices: DeviceConfig[],
  influx?: Record<string, unknown>,
): Promise<{ status: string; path: string }> {
  const r = await fetch(`${API_BASE}/admin/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ devices, influx }),
  });
  if (!r.ok) throw new Error(`Failed to update config: ${r.status}`);
  return r.json();
}

export async function updateDeviceConfig(
  devId: string,
  config: DeviceConfig,
): Promise<{ status: string; device: DeviceConfig }> {
  const r = await fetch(`${API_BASE}/admin/config/device/${encodeURIComponent(devId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!r.ok) throw new Error(`Failed to update device config: ${r.status}`);
  return r.json();
}

export async function deleteDeviceConfig(
  devId: string,
): Promise<{ status: string; removed: string }> {
  const r = await fetch(`${API_BASE}/admin/config/device/${encodeURIComponent(devId)}`, {
    method: 'DELETE',
  });
  if (!r.ok) throw new Error(`Failed to delete device: ${r.status}`);
  return r.json();
}

export async function listDrivers(): Promise<{ drivers: DriverInfo[] }> {
  const r = await fetch(`${API_BASE}/admin/drivers`);
  if (!r.ok) throw new Error(`Failed to list drivers: ${r.status}`);
  return r.json();
}
