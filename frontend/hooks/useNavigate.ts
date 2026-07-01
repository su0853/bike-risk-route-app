import { useState } from 'react';
import { fetchRoutes } from '../services/api';
import { NavigateRequest, RouteResult } from '../types/navigation';

export function useNavigate() {
  const [routes, setRoutes] = useState<RouteResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function navigate(req: NavigateRequest) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchRoutes(req);
      setRoutes(res.routes);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRoutes([]);
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setRoutes([]);
    setError(null);
  }

  return { routes, loading, error, navigate, reset };
}
