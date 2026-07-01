import React from 'react';
import { FlatList, StyleSheet, View } from 'react-native';
import { RouteResult } from '../types/navigation';
import { RouteCard } from './RouteCard';

interface Props {
  routes: RouteResult[];
  selectedIndex: number;
  onSelect: (index: number) => void;
}

export function RouteList({ routes, selectedIndex, onSelect }: Props) {
  return (
    <View style={styles.container}>
      <FlatList
        data={routes}
        keyExtractor={(item) => item.route_type}
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.list}
        renderItem={({ item, index }) => (
          <RouteCard
            route={item}
            selected={index === selectedIndex}
            onPress={() => onSelect(index)}
          />
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#f8fafc',
    paddingVertical: 12,
    borderTopWidth: 1,
    borderTopColor: '#e2e8f0',
  },
  list: {
    paddingHorizontal: 16,
  },
});
