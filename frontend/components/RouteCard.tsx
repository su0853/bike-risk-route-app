import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { RouteResult } from '../types/navigation';
import { RiskBadge } from './RiskBadge';

const ROUTE_LABEL: Record<string, string> = {
  safety_optimized: '安全路線',
  google_0: 'Google 路線 1',
  google_1: 'Google 路線 2',
};

interface Props {
  route: RouteResult;
  selected: boolean;
  onPress: () => void;
}

export function RouteCard({ route, selected, onPress }: Props) {
  const distanceKm = (route.total_distance_m / 1000).toFixed(1);
  const label = ROUTE_LABEL[route.route_type] ?? route.route_type;

  return (
    <TouchableOpacity
      style={[styles.card, selected && styles.selected]}
      onPress={onPress}
      activeOpacity={0.8}
    >
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.distance}>{distanceKm} km</Text>
      <RiskBadge category={route.risk_category} />
      <Text style={styles.score}>風險: {(route.total_risk_score * 100).toFixed(1)}%</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 14,
    marginRight: 12,
    width: 140,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  selected: {
    borderColor: '#3b82f6',
  },
  label: {
    fontSize: 13,
    fontWeight: '700',
    color: '#1e293b',
    marginBottom: 4,
  },
  distance: {
    fontSize: 18,
    fontWeight: '700',
    color: '#334155',
    marginBottom: 6,
  },
  score: {
    fontSize: 11,
    color: '#64748b',
    marginTop: 4,
  },
});
