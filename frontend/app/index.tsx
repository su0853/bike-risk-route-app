import { useRouter } from 'expo-router';
import React, { useState } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SearchForm } from '../components/SearchForm';
import { GeocoderResult } from '../services/geocoder';
import { NavigateRequest } from '../types/navigation';

export default function IndexScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  function handleSearch(startResult: GeocoderResult, endResult: GeocoderResult, lambda: number) {
    setLoading(true);
    const req: NavigateRequest = {
      start: { lat: startResult.lat, lon: startResult.lon },
      end: { lat: endResult.lat, lon: endResult.lon },
      lambda_coef: lambda,
    };
    router.push({
      pathname: '/map',
      params: { requestJson: JSON.stringify(req) },
    });
    setLoading(false);
  }

  return (
    <ScrollView style={styles.container} keyboardShouldPersistTaps="handled">
      <View style={styles.header}>
        <Text style={styles.title}>自行車安全路線</Text>
        <Text style={styles.subtitle}>輸入起終點，系統將推薦最安全的騎行路線</Text>
      </View>
      <SearchForm loading={loading} onSearch={handleSearch} />
      <TouchableOpacity
        style={styles.devBtn}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        onPress={() => router.push('/nav_prototype' as any)}
      >
        <Text style={styles.devBtnText}>[Dev] Navigation SDK Prototype</Text>
      </TouchableOpacity>

      <View style={styles.tips}>
        <Text style={styles.tipsTitle}>使用說明</Text>
        <Text style={styles.tip}>• 輸入地址後點「查詢」，從候選清單選擇正確地點</Text>
        <Text style={styles.tip}>• 安全權重 λ 越高，路線越偏向避開事故多發路段</Text>
        <Text style={styles.tip}>• 綠色路線 = 安全優化；藍色/橘色 = Google 建議路線</Text>
        <Text style={styles.tip}>• 低風險 (綠) → 中風險 (黃) → 高風險 (紅)</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8fafc',
  },
  header: {
    padding: 20,
    paddingBottom: 8,
  },
  title: {
    fontSize: 24,
    fontWeight: '800',
    color: '#0f172a',
    marginBottom: 6,
  },
  subtitle: {
    fontSize: 14,
    color: '#64748b',
    lineHeight: 20,
  },
  tips: {
    margin: 16,
    padding: 14,
    backgroundColor: '#eff6ff',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#bfdbfe',
  },
  tipsTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#1d4ed8',
    marginBottom: 8,
  },
  tip: {
    fontSize: 13,
    color: '#1e40af',
    lineHeight: 20,
  },
  devBtn: {
    marginHorizontal: 16,
    marginTop: 8,
    padding: 10,
    backgroundColor: '#1e293b',
    borderRadius: 8,
    alignItems: 'center',
  },
  devBtnText: {
    color: '#94a3b8',
    fontSize: 12,
  },
});
