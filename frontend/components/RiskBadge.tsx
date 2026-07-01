import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

type RiskCategory = 'low' | 'medium' | 'high';

const COLOR: Record<RiskCategory, string> = {
  low: '#22c55e',
  medium: '#f59e0b',
  high: '#ef4444',
};

const LABEL: Record<RiskCategory, string> = {
  low: '低風險',
  medium: '中風險',
  high: '高風險',
};

interface Props {
  category: RiskCategory;
}

export function RiskBadge({ category }: Props) {
  return (
    <View style={[styles.badge, { backgroundColor: COLOR[category] }]}>
      <Text style={styles.text}>{LABEL[category]}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 12,
    alignSelf: 'flex-start',
  },
  text: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
});
