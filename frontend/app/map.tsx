import {
  NavigationView,
  type MapViewController,
} from '@googlemaps/react-native-navigation-sdk';
import { useLocalSearchParams } from 'expo-router';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, StyleSheet, Text, View } from 'react-native';
import { RouteList } from '../components/RouteList';
import { useNavigate } from '../hooks/useNavigate';
import { NavigateRequest, RouteResult } from '../types/navigation';

const TAIPEI = { lat: 25.05, lng: 121.55 };

const ROUTE_COLORS: Record<string, string> = {
  safety_optimized: '#22c55e',
  google_0: '#3b82f6',
  google_1: '#f97316',
};

function routeColor(type: string): string {
  return ROUTE_COLORS[type] ?? '#6366f1';
}

function boundsToZoom(latDelta: number): number {
  if (latDelta > 0.3) return 10;
  if (latDelta > 0.15) return 11;
  if (latDelta > 0.08) return 12;
  if (latDelta > 0.04) return 13;
  if (latDelta > 0.02) return 14;
  return 15;
}

export default function MapScreen() {
  const params = useLocalSearchParams<{ requestJson: string }>();
  const { routes, loading, error, navigate } = useNavigate();
  const [selectedIndex, setSelectedIndex] = useState(0);
  const mapCtrlRef = useRef<MapViewController | null>(null);
  const [isMapReady, setIsMapReady] = useState(false);

  useEffect(() => {
    if (!params.requestJson) return;
    try {
      navigate(JSON.parse(params.requestJson) as NavigateRequest);
    } catch {
      Alert.alert('參數錯誤', '無法解析路線請求');
    }
  }, []);

  useEffect(() => {
    if (error) Alert.alert('路線錯誤', error);
  }, [error]);

  useEffect(() => {
    if (!isMapReady || !mapCtrlRef.current || routes.length === 0) return;
    void drawOverlays(mapCtrlRef.current, routes, selectedIndex);
  }, [routes, selectedIndex, isMapReady]);

  const onMapViewControllerCreated = useCallback((ctrl: MapViewController) => {
    mapCtrlRef.current = ctrl;
  }, []);

  const onMapReady = useCallback(() => {
    setIsMapReady(true);
  }, []);

  async function drawOverlays(
    ctrl: MapViewController,
    routeList: RouteResult[],
    selIdx: number,
  ) {
    // addPolyline with the same id updates in-place — no need to clear first
    for (let i = 0; i < routeList.length; i++) {
      const route = routeList[i];
      const isSelected = i === selIdx;
      await ctrl.addPolyline({
        id: `route_${route.route_type}`,
        points: route.waypoints.map(([lat, lon]) => ({ lat, lng: lon })),
        color: routeColor(route.route_type),
        width: isSelected ? 8 : 3,
      });
    }

    // Markers for selected route's start / end
    const selected = routeList[selIdx];
    if (selected && selected.waypoints.length > 0) {
      const first = selected.waypoints[0];
      const last = selected.waypoints[selected.waypoints.length - 1];
      await ctrl.addMarker({
        id: 'marker_start',
        position: { lat: first[0], lng: first[1] },
        title: '起點',
      });
      await ctrl.addMarker({
        id: 'marker_end',
        position: { lat: last[0], lng: last[1] },
        title: '終點',
      });
    }

    // Fit camera to bounding box of all routes
    const allCoords = routeList.flatMap((r) => r.waypoints);
    const lats = allCoords.map(([lat]) => lat);
    const lons = allCoords.map(([, lon]) => lon);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);
    ctrl.moveCamera({
      target: { lat: (minLat + maxLat) / 2, lng: (minLon + maxLon) / 2 },
      zoom: boundsToZoom(Math.max(maxLat - minLat + 0.01, (maxLon - minLon + 0.01) * 0.9)),
    });
  }

  return (
    <View style={styles.container}>
      <NavigationView
        style={styles.map}
        initialCameraPosition={{ target: TAIPEI, zoom: 12 }}
        myLocationEnabled
        myLocationButtonEnabled
        onMapViewControllerCreated={onMapViewControllerCreated}
        onMapReady={onMapReady}
        onPolylineClick={(polyline) => {
          const idx = routes.findIndex(
            (r) => `route_${r.route_type}` === polyline.id,
          );
          if (idx !== -1) setSelectedIndex(idx);
        }}
      />

      {loading && (
        <View style={styles.loadingOverlay}>
          <ActivityIndicator size="large" color="#3b82f6" />
          <Text style={styles.loadingText}>計算路線中…</Text>
        </View>
      )}

      {!loading && routes.length > 0 && (
        <RouteList
          routes={routes}
          selectedIndex={selectedIndex}
          onSelect={setSelectedIndex}
        />
      )}

      {!loading && routes.length === 0 && !error && (
        <View style={styles.emptyBanner}>
          <Text style={styles.emptyText}>找不到路線，請調整起終點</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  map: { flex: 1 },
  loadingOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(255,255,255,0.7)',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 12,
  },
  loadingText: {
    fontSize: 16,
    color: '#334155',
    fontWeight: '600',
  },
  emptyBanner: {
    padding: 16,
    backgroundColor: '#fef2f2',
    borderTopWidth: 1,
    borderTopColor: '#fecaca',
    alignItems: 'center',
  },
  emptyText: { color: '#dc2626', fontSize: 14 },
});
