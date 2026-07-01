import { useLocalSearchParams } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, StyleSheet, Text, View } from 'react-native';
import MapView, { LatLng, Marker, Polyline } from 'react-native-maps';
import { RouteList } from '../components/RouteList';
import { useMapRegion } from '../hooks/useMapRegion';
import { useNavigate } from '../hooks/useNavigate';
import { NavigateRequest, RouteResult } from '../types/navigation';

const ROUTE_COLORS: Record<string, string> = {
  safety_optimized: '#22c55e',
  google_0: '#3b82f6',
  google_1: '#f97316',
};

function routeColor(routeType: string): string {
  return ROUTE_COLORS[routeType] ?? '#6366f1';
}

export default function MapScreen() {
  const params = useLocalSearchParams<{ requestJson: string }>();
  const { routes, loading, error, navigate } = useNavigate();
  const { region, fitToRoutes } = useMapRegion();
  const [selectedIndex, setSelectedIndex] = useState(0);

  useEffect(() => {
    if (!params.requestJson) return;
    try {
      const req: NavigateRequest = JSON.parse(params.requestJson);
      navigate(req);
    } catch {
      Alert.alert('參數錯誤', '無法解析路線請求');
    }
  }, []);

  useEffect(() => {
    if (routes.length > 0) {
      fitToRoutes(routes);
      setSelectedIndex(0);
    }
  }, [routes]);

  useEffect(() => {
    if (error) Alert.alert('路線錯誤', error);
  }, [error]);

  const selectedRoute: RouteResult | undefined = routes[selectedIndex];

  const startPoint: LatLng | null = selectedRoute?.waypoints[0]
    ? { latitude: selectedRoute.waypoints[0][0], longitude: selectedRoute.waypoints[0][1] }
    : null;

  const endPoint: LatLng | null = selectedRoute?.waypoints[selectedRoute.waypoints.length - 1]
    ? {
        latitude: selectedRoute.waypoints[selectedRoute.waypoints.length - 1][0],
        longitude: selectedRoute.waypoints[selectedRoute.waypoints.length - 1][1],
      }
    : null;

  return (
    <View style={styles.container}>
      <MapView style={styles.map} region={region} showsUserLocation>
        {routes.map((route, idx) => (
          <Polyline
            key={route.route_type}
            coordinates={route.waypoints.map(([lat, lon]) => ({ latitude: lat, longitude: lon }))}
            strokeColor={routeColor(route.route_type)}
            strokeWidth={idx === selectedIndex ? 5 : 2}
            tappable
            onPress={() => setSelectedIndex(idx)}
          />
        ))}
        {startPoint && (
          <Marker coordinate={startPoint} title="起點" pinColor="green" />
        )}
        {endPoint && (
          <Marker coordinate={endPoint} title="終點" pinColor="red" />
        )}
      </MapView>

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
  container: {
    flex: 1,
  },
  map: {
    flex: 1,
  },
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
  emptyText: {
    color: '#dc2626',
    fontSize: 14,
  },
});
