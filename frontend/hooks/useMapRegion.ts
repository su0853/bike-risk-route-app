import { useState } from 'react';
import { RouteResult } from '../types/navigation';

export interface Region {
  latitude: number;
  longitude: number;
  latitudeDelta: number;
  longitudeDelta: number;
}

const TAIPEI_REGION: Region = {
  latitude: 25.05,
  longitude: 121.55,
  latitudeDelta: 0.15,
  longitudeDelta: 0.15,
};

export function useMapRegion() {
  const [region, setRegion] = useState<Region>(TAIPEI_REGION);

  function fitToRoutes(routes: RouteResult[]) {
    if (!routes.length) return;
    const allCoords = routes.flatMap((r) => r.waypoints);
    if (!allCoords.length) return;

    const lats = allCoords.map(([lat]) => lat);
    const lons = allCoords.map(([, lon]) => lon);
    const padding = 0.01;
    setRegion({
      latitude: (Math.min(...lats) + Math.max(...lats)) / 2,
      longitude: (Math.min(...lons) + Math.max(...lons)) / 2,
      latitudeDelta: Math.max(...lats) - Math.min(...lats) + padding,
      longitudeDelta: Math.max(...lons) - Math.min(...lons) + padding,
    });
  }

  return { region, setRegion, fitToRoutes };
}
