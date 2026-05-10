/**
 * SelectionContext — shared, persisted IntelligentPropertyPicker selection (v2.5).
 *
 * One canonical selection per logged-in user, persisted to localStorage so a
 * pick made in Ad Copy survives a hard reload AND propagates to CRM,
 * Marketing Calendar, and the Hub identity strip without per-page re-picking.
 *
 * Shape mirrors what the picker emits:
 *   { scope, hotel_ids, brand_ids, cities, is_loyalty, _labels: { hotels, brands, cities } }
 */
import { createContext, useContext, useEffect, useState, useCallback } from 'react';

const KEY = 'vantage.selection.v1';
const SelectionContext = createContext(null);

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    // Sanity — picker selections are objects with at least one of these arrays.
    if (!parsed || typeof parsed !== 'object') return null;
    return parsed;
  } catch {
    return null;
  }
}

export function SelectionProvider({ children }) {
  const [selection, setSelectionState] = useState(loadFromStorage);

  const setSelection = useCallback((next) => {
    setSelectionState(next);
    try {
      if (next == null) localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      /* quota / privacy mode — fine, in-memory only */
    }
  }, []);

  // If the user logs out (token cleared), drop the selection too.
  useEffect(() => {
    const onStorage = (e) => {
      if (e.key === 'token' && !e.newValue) {
        setSelectionState(null);
        try { localStorage.removeItem(KEY); } catch {}
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  return (
    <SelectionContext.Provider value={{ selection, setSelection }}>
      {children}
    </SelectionContext.Provider>
  );
}

export function useSelection() {
  const ctx = useContext(SelectionContext);
  if (!ctx) throw new Error('useSelection must be used inside <SelectionProvider>');
  return ctx;
}
