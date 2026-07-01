import { useLocalSearchParams } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { NavigateRequest, NavigateResponse } from '../types/navigation';

const BASE = process.env.EXPO_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export default function MapWebScreen() {
  const params = useLocalSearchParams<{ requestJson: string }>();

  const [status, setStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle');
  const [rawResponse, setRawResponse] = useState<string>('');
  const [parsedData, setParsedData] = useState<NavigateResponse | null>(null);
  const [fetchError, setFetchError] = useState<string>('');
  const [parsedRequest, setParsedRequest] = useState<NavigateRequest | null>(null);

  // 直接 fetch，完全繞過 hook，確認最底層是否有回資料
  useEffect(() => {
    if (!params.requestJson) return;

    let req: NavigateRequest;
    try {
      req = JSON.parse(params.requestJson);
      setParsedRequest(req);
    } catch (e) {
      setStatus('error');
      setFetchError(`JSON.parse 失敗: ${e}`);
      return;
    }

    setStatus('loading');
    fetch(`${BASE}/api/navigate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    })
      .then(async (res) => {
        const text = await res.text();
        setRawResponse(text);
        if (!res.ok) {
          setStatus('error');
          setFetchError(`HTTP ${res.status}`);
          return;
        }
        const data: NavigateResponse = JSON.parse(text);
        setParsedData(data);
        setStatus('done');
      })
      .catch((e) => {
        setStatus('error');
        setFetchError(`fetch 失敗: ${e}`);
      });
  }, []);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* ── 解析後座標 ── */}
      <Section title="📍 geocoded 座標">
        {parsedRequest ? (
          <>
            <Mono>{`起點: lat=${parsedRequest.start.lat.toFixed(6)}, lon=${parsedRequest.start.lon.toFixed(6)}`}</Mono>
            <Mono>{`終點: lat=${parsedRequest.end.lat.toFixed(6)}, lon=${parsedRequest.end.lon.toFixed(6)}`}</Mono>
            <Mono>{`λ = ${parsedRequest.lambda_coef}`}</Mono>
          </>
        ) : (
          <Mono>（等待中）</Mono>
        )}
      </Section>

      {/* ── API URL ── */}
      <Section title="🌐 API endpoint">
        <Mono>{`POST ${BASE}/api/navigate`}</Mono>
      </Section>

      {/* ── 狀態 ── */}
      <Section title="⚙️ 狀態">
        <Mono>{status}</Mono>
        {status === 'loading' && <ActivityIndicator style={{ marginTop: 8 }} />}
        {status === 'error' && <Mono style={styles.errorText}>{fetchError}</Mono>}
      </Section>

      {/* ── 原始回應（前 500 字）── */}
      {rawResponse !== '' && (
        <Section title="📄 原始回應（前 500 字元）">
          <Mono>{rawResponse.slice(0, 500)}</Mono>
        </Section>
      )}

      {/* ── 解析結果摘要 ── */}
      {parsedData && (
        <Section title={`✅ 解析成功 — ${parsedData.routes.length} 條路線`}>
          {parsedData.routes.map((r) => (
            <View key={r.route_type} style={styles.routeCard}>
              <Text style={styles.routeTitle}>{r.route_type}</Text>
              <Mono>{`距離: ${(r.total_distance_m / 1000).toFixed(2)} km`}</Mono>
              <Mono>{`風險: ${(r.total_risk_score * 100).toFixed(2)}% (${r.risk_category})`}</Mono>
              <Mono>{`座標點: ${r.waypoints.length}`}</Mono>
            </View>
          ))}
        </Section>
      )}
    </ScrollView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function Mono({ children, style }: { children: React.ReactNode; style?: object }) {
  return <Text style={[styles.mono, style]}>{children}</Text>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  content: { padding: 16, gap: 12 },
  section: {
    backgroundColor: '#1e293b',
    borderRadius: 8,
    padding: 12,
    gap: 6,
  },
  sectionTitle: {
    color: '#94a3b8',
    fontSize: 12,
    fontWeight: '700',
    marginBottom: 4,
    textTransform: 'uppercase',
  },
  mono: {
    color: '#e2e8f0',
    fontFamily: 'monospace',
    fontSize: 13,
    lineHeight: 20,
  },
  errorText: {
    color: '#f87171',
  },
  routeCard: {
    backgroundColor: '#0f172a',
    borderRadius: 6,
    padding: 10,
    gap: 4,
    marginTop: 4,
  },
  routeTitle: {
    color: '#38bdf8',
    fontWeight: '700',
    fontSize: 14,
    marginBottom: 4,
  },
});
