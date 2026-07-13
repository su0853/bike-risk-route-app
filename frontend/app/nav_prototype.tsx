/**
 * Map Display Test
 *
 * 驗證目標（縮小範圍）：
 *   - NavigationView 在無 init() 的情況下，tiles 是否會載入？
 *   - onMapReady 是否正確觸發？
 *   - moveCamera 能否在 onMapReady 後移動鏡頭？
 *
 * 預期假設：NavigationView 不呼叫 init() → tiles 不載入（米白）
 * 若確認為真 → map.tsx 改用 MapView（不需要 init）
 */
import {
  MapView,
  NavigationView,
  type MapViewController,
} from '@googlemaps/react-native-navigation-sdk';
import { useRouter } from 'expo-router';
import React, { useCallback, useRef, useState } from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';

const TAIPEI_101 = { lat: 25.0339, lng: 121.5645 };
const TAIPEI_CENTER = { lat: 25.05, lng: 121.55 };

export default function NavPrototypeScreen() {
  const router = useRouter();
  const [log, setLog] = useState<string[]>(['等待地圖事件...']);
  const [navTilesLoaded, setNavTilesLoaded] = useState<boolean | null>(null);
  const [mapTilesLoaded, setMapTilesLoaded] = useState<boolean | null>(null);
  const navCtrlRef = useRef<MapViewController | null>(null);
  const mapCtrlRef = useRef<MapViewController | null>(null);

  function addLog(msg: string) {
    setLog(prev => [`[${new Date().toLocaleTimeString()}] ${msg}`, ...prev.slice(0, 29)]);
  }

  // --- NavigationView callbacks (無 init) ---
  const onNavControllerCreated = useCallback((ctrl: MapViewController) => {
    navCtrlRef.current = ctrl;
    addLog('NavigationView: controller 取得');
  }, []);

  const onNavMapReady = useCallback(() => {
    addLog('NavigationView: onMapReady 觸發 ✅ → 移動鏡頭');
    setNavTilesLoaded(true);
    navCtrlRef.current?.moveCamera({ target: TAIPEI_101, zoom: 15 });
  }, []);

  // --- MapView callbacks ---
  const onMapControllerCreated = useCallback((ctrl: MapViewController) => {
    mapCtrlRef.current = ctrl;
    addLog('MapView: controller 取得');
  }, []);

  const onMapViewReady = useCallback(() => {
    addLog('MapView: onMapReady 觸發 ✅ → 移動鏡頭');
    setMapTilesLoaded(true);
    mapCtrlRef.current?.moveCamera({ target: TAIPEI_101, zoom: 15 });
  }, []);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backBtnText}>← 返回</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Map Display Test</Text>
      </View>

      <View style={styles.mapsRow}>
        {/* 左：NavigationView（無 init）*/}
        <View style={styles.mapCell}>
          <Text style={styles.mapLabel}>
            NavigationView{'\n'}
            <Text style={labelStatus(navTilesLoaded)}>
              {navTilesLoaded === null ? '等待...' : navTilesLoaded ? '✅ Ready' : '❌ 未就緒'}
            </Text>
          </Text>
          <NavigationView
            style={styles.mapView}
            initialCameraPosition={{ target: TAIPEI_CENTER, zoom: 12 }}
            onMapViewControllerCreated={onNavControllerCreated}
            onMapReady={onNavMapReady}
          />
        </View>

        {/* 右：MapView */}
        <View style={styles.mapCell}>
          <Text style={styles.mapLabel}>
            MapView{'\n'}
            <Text style={labelStatus(mapTilesLoaded)}>
              {mapTilesLoaded === null ? '等待...' : mapTilesLoaded ? '✅ Ready' : '❌ 未就緒'}
            </Text>
          </Text>
          <MapView
            style={styles.mapView}
            initialCameraPosition={{ target: TAIPEI_CENTER, zoom: 12 }}
            onMapViewControllerCreated={onMapControllerCreated}
            onMapReady={onMapViewReady}
          />
        </View>
      </View>

      <ScrollView style={styles.logBox} contentContainerStyle={styles.logContent}>
        {log.map((line, i) => (
          <Text key={i} style={styles.logLine}>{line}</Text>
        ))}
      </ScrollView>
    </View>
  );
}

function labelStatus(loaded: boolean | null) {
  if (loaded === null) return styles.statusWait;
  return loaded ? styles.statusOk : styles.statusErr;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  header: {
    flexDirection: 'row', alignItems: 'center', padding: 12, paddingTop: 48,
    backgroundColor: '#1e293b', gap: 8,
  },
  backBtn: { paddingHorizontal: 4 },
  backBtnText: { color: '#94a3b8', fontSize: 14 },
  title: { flex: 1, color: '#f1f5f9', fontSize: 15, fontWeight: '700' },
  mapsRow: { flex: 1, flexDirection: 'row' },
  mapCell: { flex: 1 },
  mapLabel: {
    backgroundColor: '#1e293b', color: '#cbd5e1', fontSize: 11,
    textAlign: 'center', paddingVertical: 4,
  },
  mapView: { flex: 1 },
  statusWait: { color: '#94a3b8' },
  statusOk: { color: '#22c55e' },
  statusErr: { color: '#ef4444' },
  logBox: { height: 200, backgroundColor: '#020617' },
  logContent: { padding: 10 },
  logLine: {
    color: '#94a3b8', fontSize: 11, fontFamily: 'monospace', marginBottom: 2,
  },
});
