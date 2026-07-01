import { useState } from 'react';
import { Region } from 'react-native-maps';
import { RouteResult } from '../types/navigation';

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
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);

    const padding = 0.01;
    setRegion({
      latitude: (minLat + maxLat) / 2,
      longitude: (minLon + maxLon) / 2,
      latitudeDelta: maxLat - minLat + padding,
      longitudeDelta: maxLon - minLon + padding,
    });
  }

  return { region, setRegion, fitToRoutes };
}
