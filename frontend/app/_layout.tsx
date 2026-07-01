import { Stack } from 'expo-router';

export default function RootLayout() {
  return (
    <Stack>
      <Stack.Screen name="index" options={{ title: '自行車安全導航' }} />
      <Stack.Screen name="map" options={{ title: '路線地圖', headerBackTitle: '返回' }} />
    </Stack>
  );
}
