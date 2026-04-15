/**
 * Profile API client for profile management
 */

const API_BASE = '/api/v2';

// ===== Types =====

export interface PropertyInfo {
  value: unknown;
  policy: 'read' | 'write';
  read_only?: boolean;
}

export interface DeviceState {
  id: string;
  driver: string;
  status: 'connected' | 'disconnected' | 'unhealthy';
  state: Record<string, unknown>;
}

export interface PropMeta {
  doc?: string;
  type?: string;
  read_only?: boolean;
  min?: number;
  max?: number;
  step?: number;
  choices?: string[];
  unit?: string;
}

export interface DeviceSpec {
  id?: string;
  driver?: string;
  properties: Record<string, PropMeta>;
  commands?: Record<string, unknown>;
  children?: Record<string, DeviceSpec>;
}

export interface ProfileResponse {
  path: string | null;
  raw: string;
  policies: Record<string, Record<string, string>>; // {dev_id: {prop_name: policy}}
}

// ===== Helpers =====

function encodePath(path: string): string {
  return path.split('/').map(encodeURIComponent).join('/');
}

// ===== API Functions =====

/**
 * Get current profile information
 */
export async function getProfile(): Promise<ProfileResponse> {
  const r = await fetch(`${API_BASE}/admin/profile`);
  if (!r.ok) throw new Error(`Failed to get profile: ${r.status}`);
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
 * Get device specification (property metadata)
 */
export async function getDeviceSpec(devId: string): Promise<DeviceSpec> {
  const r = await fetch(`${API_BASE}/devices/${encodePath(devId)}/spec`);
  if (!r.ok) throw new Error(`Failed to get device spec: ${r.status}`);
  return r.json();
}

/**
 * Set property policy
 */
export async function setPropertyPolicy(
  devId: string,
  propName: string,
  policy: 'read' | 'write'
): Promise<{ status: string; dev_id: string; prop_name: string; policy: string }> {
  const params = new URLSearchParams({
    dev_id: devId,
    prop_name: propName,
    policy,
  });
  const r = await fetch(`${API_BASE}/admin/profile/policy?${params}`, {
    method: 'POST',
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`Failed to set policy: ${text}`);
  }
  return r.json();
}

/**
 * Force save profile
 */
export async function saveProfile(): Promise<{ status: string; profile_path: string }> {
  const r = await fetch(`${API_BASE}/admin/profile/save`, { method: 'POST' });
  if (!r.ok) throw new Error(`Failed to save profile: ${r.status}`);
  return r.json();
}

/**
 * Download profile as YAML file
 */
export function downloadProfile(raw: string, filename = 'profile.yaml'): void {
  const blob = new Blob([raw], { type: 'text/yaml' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
