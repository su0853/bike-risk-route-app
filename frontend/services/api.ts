import { NavigateRequest, NavigateResponse } from '../types/navigation';

const BASE = process.env.EXPO_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export async function fetchRoutes(req: NavigateRequest): Promise<NavigateResponse> {
  const res = await fetch(`${BASE}/api/navigate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

export async function fetchHealth(): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/api/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}
