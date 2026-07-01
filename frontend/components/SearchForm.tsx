import Slider from '@react-native-community/slider';
import * as Location from 'expo-location';
import React, { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { GeocoderResult, geocodeAddressCandidates } from '../services/geocoder';

interface Props {
  loading: boolean;
  onSearch: (start: GeocoderResult, end: GeocoderResult, lambda: number) => void;
}

interface FieldState {
  text: string;
  candidates: GeocoderResult[];
  selected: GeocoderResult | null;
  searching: boolean;
}

const EMPTY: FieldState = { text: '', candidates: [], selected: null, searching: false };

export function SearchForm({ loading, onSearch }: Props) {
  const [start, setStart] = useState<FieldState>(EMPTY);
  const [end, setEnd] = useState<FieldState>(EMPTY);
  const [lambda, setLambda] = useState(0.5);
  const [locating, setLocating] = useState(false);

  async function useCurrentLocation() {
    setLocating(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('定位權限', '請在設定中允許存取位置才能使用此功能');
        return;
      }
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const result: GeocoderResult = {
        lat: pos.coords.latitude,
        lon: pos.coords.longitude,
        displayName: '目前位置',
      };
      setStart({ text: '目前位置', candidates: [], selected: result, searching: false });
    } catch {
      Alert.alert('定位失敗', '無法取得目前位置，請確認 GPS 是否已開啟');
    } finally {
      setLocating(false);
    }
  }

  async function lookup(
    field: FieldState,
    setField: React.Dispatch<React.SetStateAction<FieldState>>,
  ) {
    if (!field.text.trim()) return;
    setField(f => ({ ...f, searching: true, candidates: [], selected: null }));
    try {
      const results = await geocodeAddressCandidates(field.text.trim());
      setField(f => ({ ...f, searching: false, candidates: results }));
    } catch (err) {
      setField(f => ({ ...f, searching: false }));
      Alert.alert('查詢失敗', err instanceof Error ? err.message : String(err));
    }
  }

  function pick(
    result: GeocoderResult,
    setField: React.Dispatch<React.SetStateAction<FieldState>>,
  ) {
    const shortName = result.displayName.split(',')[0].trim();
    setField({ text: shortName, candidates: [], selected: result, searching: false });
  }

  function clear(setField: React.Dispatch<React.SetStateAction<FieldState>>) {
    setField(EMPTY);
  }

  function renderField(
    placeholder: string,
    field: FieldState,
    setField: React.Dispatch<React.SetStateAction<FieldState>>,
    showLocateBtn = false,
  ) {
    return (
      <View style={styles.fieldBlock}>
        <View style={styles.inputRow}>
          {showLocateBtn && (
            <TouchableOpacity
              style={[styles.locateBtn, locating && styles.locateBtnDisabled]}
              onPress={useCurrentLocation}
              disabled={locating}
            >
              {locating ? (
                <ActivityIndicator size="small" color="#3b82f6" />
              ) : (
                <Text style={styles.locateBtnText}>定位</Text>
              )}
            </TouchableOpacity>
          )}
          <TextInput
            style={[styles.input, !!field.selected && styles.inputSelected]}
            placeholder={placeholder}
            placeholderTextColor="#94a3b8"
            value={field.text}
            onChangeText={text =>
              setField(f => ({ ...f, text, selected: null, candidates: [] }))
            }
            returnKeyType="search"
            onSubmitEditing={() => lookup(field, setField)}
            editable={!field.selected}
          />
          {field.selected ? (
            <TouchableOpacity style={styles.clearBtn} onPress={() => clear(setField)}>
              <Text style={styles.clearBtnText}>×</Text>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity
              style={[
                styles.lookupBtn,
                (!field.text.trim() || field.searching) && styles.lookupBtnDisabled,
              ]}
              onPress={() => lookup(field, setField)}
              disabled={!field.text.trim() || field.searching}
            >
              {field.searching ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <Text style={styles.lookupBtnText}>查詢</Text>
              )}
            </TouchableOpacity>
          )}
        </View>

        {field.candidates.length > 0 && (
          <View style={styles.candidateBox}>
            {field.candidates.map((r, i) => (
              <TouchableOpacity
                key={i}
                style={[
                  styles.candidateItem,
                  i < field.candidates.length - 1 && styles.candidateDivider,
                ]}
                onPress={() => pick(r, setField)}
              >
                <Text style={styles.candidatePrimary} numberOfLines={1}>
                  {r.displayName.split(',')[0].trim()}
                </Text>
                <Text style={styles.candidateSecondary} numberOfLines={1}>
                  {r.displayName}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        )}
      </View>
    );
  }

  const canSearch = !!start.selected && !!end.selected && !loading;

  return (
    <View style={styles.container}>
      {renderField('起點地址', start, setStart, true)}
      {renderField('終點地址', end, setEnd)}

      <View style={styles.sliderRow}>
        <Text style={styles.sliderLabel}>安全權重 λ: {lambda.toFixed(1)}</Text>
        <Slider
          style={styles.slider}
          minimumValue={0}
          maximumValue={5}
          step={0.1}
          value={lambda}
          onValueChange={setLambda}
          minimumTrackTintColor="#3b82f6"
          maximumTrackTintColor="#cbd5e1"
        />
      </View>

      <TouchableOpacity
        style={[styles.button, !canSearch && styles.buttonDisabled]}
        onPress={() => start.selected && end.selected && onSearch(start.selected, end.selected, lambda)}
        disabled={!canSearch}
      >
        {loading ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.buttonText}>搜尋路線</Text>
        )}
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    padding: 16,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
  },
  fieldBlock: {
    marginBottom: 10,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 8,
    padding: 10,
    fontSize: 15,
    color: '#1e293b',
  },
  inputSelected: {
    borderColor: '#22c55e',
    backgroundColor: '#f0fdf4',
  },
  lookupBtn: {
    backgroundColor: '#3b82f6',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
    justifyContent: 'center',
    alignItems: 'center',
    minWidth: 56,
  },
  lookupBtnDisabled: {
    backgroundColor: '#93c5fd',
  },
  lookupBtnText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  clearBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#e2e8f0',
    justifyContent: 'center',
    alignItems: 'center',
  },
  clearBtnText: {
    fontSize: 18,
    color: '#475569',
    lineHeight: 20,
  },
  candidateBox: {
    marginTop: 4,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 8,
    backgroundColor: '#fff',
    overflow: 'hidden',
  },
  candidateItem: {
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  candidateDivider: {
    borderBottomWidth: 1,
    borderBottomColor: '#f1f5f9',
  },
  candidatePrimary: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1e293b',
  },
  candidateSecondary: {
    fontSize: 12,
    color: '#94a3b8',
    marginTop: 2,
  },
  locateBtn: {
    width: 44,
    height: 44,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#3b82f6',
    justifyContent: 'center',
    alignItems: 'center',
  },
  locateBtnDisabled: {
    borderColor: '#93c5fd',
  },
  locateBtnText: {
    fontSize: 12,
    color: '#3b82f6',
    fontWeight: '600',
  },
  sliderRow: {
    marginBottom: 12,
    marginTop: 4,
  },
  sliderLabel: {
    fontSize: 13,
    color: '#475569',
    marginBottom: 4,
  },
  slider: {
    width: '100%',
    height: 32,
  },
  button: {
    backgroundColor: '#3b82f6',
    borderRadius: 10,
    paddingVertical: 13,
    alignItems: 'center',
  },
  buttonDisabled: {
    backgroundColor: '#cbd5e1',
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
});
