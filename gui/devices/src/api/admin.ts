/**
 * Admin API client for config management
 */

const API_BASE = '/api/v2';

// ===== Types =====

export interface DeviceConfig {
  id: string;
  driver: string;
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

export interface DeviceState {
  id: string;
  driver: string;
  status: 'connected' | 'disconnected' | 'unhealthy';
  state: Record<string, unknown>;
}

export interface SoftReloadResult {
  status: string;
  added: string[];
  removed: string[];
  restarted: string[];
  unchanged: string[];
  devices: DeviceState[];
}

// ===== API Functions =====

/**
 * Get current configuration
 */
export async function getConfig(): Promise<ConfigResponse> {
  const r = await fetch(`${API_BASE}/admin/config`);
  if (!r.ok) throw new Error(`Failed to get config: ${r.status}`);
  return r.json();
}

/**
 * Update entire configuration
 */
export async function updateConfig(
  devices: DeviceConfig[],
  influx?: Record<string, unknown>
): Promise<{ status: string; path: string }> {
  const r = await fetch(`${API_BASE}/admin/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ devices, influx }),
  });
  if (!r.ok) throw new Error(`Failed to update config: ${r.status}`);
  return r.json();
}

/**
 * Get single device config
 */
export async function getDeviceConfig(
  devId: string
): Promise<{ device: DeviceConfig }> {
  const r = await fetch(`${API_BASE}/admin/config/device/${devId}`);
  if (!r.ok) throw new Error(`Failed to get device config: ${r.status}`);
  return r.json();
}

/**
 * Update single device config
 */
export async function updateDeviceConfig(
  devId: string,
  config: DeviceConfig
): Promise<{ status: string; device: DeviceConfig }> {
  const r = await fetch(`${API_BASE}/admin/config/device/${devId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!r.ok) throw new Error(`Failed to update device config: ${r.status}`);
  return r.json();
}

/**
 * Delete device from config
 */
export async function deleteDeviceConfig(
  devId: string
): Promise<{ status: string; removed: string }> {
  const r = await fetch(`${API_BASE}/admin/config/device/${devId}`, {
    method: 'DELETE',
  });
  if (!r.ok) throw new Error(`Failed to delete device: ${r.status}`);
  return r.json();
}

/**
 * List available drivers
 */
export async function listDrivers(): Promise<{ drivers: DriverInfo[] }> {
  const r = await fetch(`${API_BASE}/admin/drivers`);
  if (!r.ok) throw new Error(`Failed to list drivers: ${r.status}`);
  return r.json();
}

/**
 * Get all devices with their runtime state
 */
export async function listDevices(): Promise<DeviceState[]> {
  const r = await fetch(`${API_BASE}/devices`);
  if (!r.ok) throw new Error(`Failed to list devices: ${r.status}`);
  return r.json();
}

/**
 * Soft reload - apply config changes intelligently
 */
export async function softReload(): Promise<SoftReloadResult> {
  const r = await fetch(`${API_BASE}/admin/soft-reload`, { method: 'POST' });
  if (!r.ok) throw new Error(`Failed to soft reload: ${r.status}`);
  return r.json();
}

/**
 * Reload a single device
 */
export async function reloadDevice(
  devId: string
): Promise<{ ok: boolean; devices: DeviceState[] }> {
  const r = await fetch(`${API_BASE}/admin/reload/${devId}`, { method: 'POST' });
  if (!r.ok) throw new Error(`Failed to reload device: ${r.status}`);
  return r.json();
}

/**
 * Connect a device (set should_connect=true, start device)
 */
export async function connectDevice(
  devId: string
): Promise<{ status: string; devices: DeviceState[] }> {
  const r = await fetch(`${API_BASE}/admin/device/${devId}/connect`, {
    method: 'POST',
  });
  if (!r.ok) throw new Error(`Failed to connect device: ${r.status}`);
  return r.json();
}

/**
 * Disconnect a device (stop device, set should_connect=false)
 */
export async function disconnectDevice(
  devId: string
): Promise<{ status: string; devices: DeviceState[] }> {
  const r = await fetch(`${API_BASE}/admin/device/${devId}/disconnect`, {
    method: 'POST',
  });
  if (!r.ok) throw new Error(`Failed to disconnect device: ${r.status}`);
  return r.json();
}

/**
 * Download config as YAML file
 */
export function downloadConfig(raw: string, filename = 'config.yaml'): void {
  const blob = new Blob([raw], { type: 'text/yaml' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
