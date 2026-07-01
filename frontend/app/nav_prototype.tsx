/**
 * Navigation SDK Prototype
 *
 * 驗證目標：
 *   1. NavigationView 能否在目前環境中渲染
 *   2. showTermsAndConditionsDialog + init() 流程是否可用
 *   3. 能否以座標設定目的地並啟動導航
 *   4. 確認 SDK 是否需要 prebuild（此頁面在 Expo Go 下應直接 crash）
 *
 * 此頁面不替換現有 map.tsx，僅作技術驗證。
 */
import {
  NavigationView,
  TaskRemovedBehavior,
  useNavigationController,
  type NavigationViewController,
} from '@googlemaps/react-native-navigation-sdk';
import { useRouter } from 'expo-router';
import React, { useEffect, useRef, useState } from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';

// 測試目的地：台北 101
const DEST_101 = { position: { lat: 25.0339, lng: 121.5645 } };

type Status = 'idle' | 'initializing' | 'ready' | 'navigating' | 'error';

export default function NavPrototypeScreen() {
  const router = useRouter();
  const [status, setStatus] = useState<Status>('idle');
  const [log, setLog] = useState<string[]>(['等待初始化...']);
  const navViewControllerRef = useRef<NavigationViewController | null>(null);

  const {
    navigationController,
    setOnArrival,
    setOnNavigationReady,
    setOnRouteChanged,
    removeAllListeners,
  } = useNavigationController(
    { title: 'Navigation Terms', companyName: 'Bike Risk Route' },
    TaskRemovedBehavior.CONTINUE_SERVICE,
  );

  function addLog(msg: string) {
    setLog(prev => [`[${new Date().toLocaleTimeString()}] ${msg}`, ...prev.slice(0, 19)]);
  }

  useEffect(() => {
    setOnNavigationReady(() => addLog('✅ Navigation session ready'));
    setOnArrival(e => {
      addLog(`✅ 抵達: ${JSON.stringify(e.waypoint)}`);
      setStatus('ready');
    });
    setOnRouteChanged(() => addLog('路線已更新'));
    return () => removeAllListeners();
  }, []);

  async function initialize() {
    setStatus('initializing');
    addLog('顯示服務條款對話框...');
    try {
      const accepted = await navigationController.showTermsAndConditionsDialog();
      if (!accepted) {
        addLog('⚠️ 使用者未接受服務條款');
        setStatus('idle');
        return;
      }
      addLog('條款已接受，呼叫 init()...');
      await navigationController.init();
      setStatus('ready');
      addLog('✅ SDK 初始化完成');
    } catch (e) {
      setStatus('error');
      addLog(`❌ 初始化失敗: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function startNavigation() {
    addLog(`設定目的地: 台北 101 (${DEST_101.position.lat}, ${DEST_101.position.lng})`);
    try {
      await navigationController.setDestination(DEST_101);
      await navigationController.startGuidance();
      setStatus('navigating');
      addLog('✅ 導航啟動');
    } catch (e) {
      addLog(`❌ 導航失敗: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backBtnText}>← 返回</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Navigation SDK Prototype</Text>
        <View style={[styles.dot, dotColor(status)]} />
      </View>

      {/* NavigationView */}
      <NavigationView
        style={styles.navView}
        onNavigationViewControllerCreated={ctrl => {
          navViewControllerRef.current = ctrl;
          addLog('✅ NavigationView 已渲染，controller 取得');
        }}
      />

      {/* Controls */}
      <View style={styles.controls}>
        <TouchableOpacity
          style={[styles.btn, status !== 'idle' && styles.btnOff]}
          onPress={initialize}
          disabled={status !== 'idle'}
        >
          <Text style={styles.btnText}>1. 初始化 SDK</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.btn, status !== 'ready' && styles.btnOff]}
          onPress={startNavigation}
          disabled={status !== 'ready'}
        >
          <Text style={styles.btnText}>2. 導航至 101</Text>
        </TouchableOpacity>
      </View>

      {/* Log */}
      <ScrollView style={styles.logBox}>
        {log.map((line, i) => (
          <Text key={i} style={styles.logLine}>{line}</Text>
        ))}
      </ScrollView>
    </View>
  );
}

function dotColor(s: Status) {
  return (
    { idle: styles.dotIdle, initializing: styles.dotWarn, ready: styles.dotOk, navigating: styles.dotOk, error: styles.dotErr }[s]
  );
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
  dot: { width: 10, height: 10, borderRadius: 5 },
  dotIdle: { backgroundColor: '#64748b' },
  dotWarn: { backgroundColor: '#f59e0b' },
  dotOk: { backgroundColor: '#22c55e' },
  dotErr: { backgroundColor: '#ef4444' },
  navView: { flex: 1 },
  controls: {
    flexDirection: 'row', padding: 10, gap: 8, backgroundColor: '#1e293b',
  },
  btn: {
    flex: 1, backgroundColor: '#3b82f6', borderRadius: 8,
    paddingVertical: 10, alignItems: 'center',
  },
  btnOff: { backgroundColor: '#334155' },
  btnText: { color: '#fff', fontSize: 13, fontWeight: '600' },
  logBox: { height: 160, backgroundColor: '#020617', padding: 10 },
  logLine: { color: '#94a3b8', fontSize: 11, fontFamily: 'monospace', marginBottom: 2 },
});
