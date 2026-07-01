const BASE = process.env.EXPO_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export interface GeocoderResult {
  lat: number;
  lon: number;
  displayName: string;
}

async function _fetchCandidates(address: string): Promise<GeocoderResult[]> {
  const url = `${BASE}/api/geocode?q=${encodeURIComponent(address)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Geocoder HTTP ${res.status}`);
  const data: Array<{ lat: number; lon: number; display_name: string }> = await res.json();
  return data.map(r => ({ lat: r.lat, lon: r.lon, displayName: r.display_name }));
}

export async function geocodeAddressCandidates(address: string): Promise<GeocoderResult[]> {
  const results = await _fetchCandidates(address);
  if (!results.length) throw new Error(`找不到地址：${address}`);
  return results;
}

export async function geocodeAddress(address: string): Promise<GeocoderResult> {
  const results = await _fetchCandidates(address);
  if (!results.length) throw new Error(`找不到地址：${address}`);
  return results[0];
}
