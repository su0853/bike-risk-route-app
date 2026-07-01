export interface RouteResult {
  route_type: string;
  geometry: {
    type: 'LineString';
    coordinates: [number, number][];
  };
  total_distance_m: number;
  total_risk_score: number;
  risk_category: 'low' | 'medium' | 'high';
  waypoints: [number, number][];
}

export interface NavigateRequest {
  start: { lat: number; lon: number };
  end: { lat: number; lon: number };
  lambda_coef?: number;
}

export interface NavigateResponse {
  routes: RouteResult[];
  status: string;
}
