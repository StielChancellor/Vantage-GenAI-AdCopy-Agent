/**
 * PropertySwitcher — cascading brand → hotel typeahead (v2.2).
 *
 * Behavior:
 *   - Type → fetches from /api/v1/admin/scope-search (admin) or /api/v1/hotels/scope-search (everyone else)
 *   - Each row is rendered as `BRAND · Hotel name`; brand row has a red "brand" badge
 *   - Selecting a HOTEL → onChange({ scope: 'hotel', hotel_id, brand_id }) and visually
 *     half-fills the brand chip + fully selects the hotel chip
 *   - Selecting a BRAND → onChange({ scope: 'brand', brand_id }) — visually one solid brand chip
 *   - Read-only mode locks the input to the assigned hotel (used for hotel_marketing_manager)
 */
import { useEffect, useRef, useState } from 'react';
import api, { } from '../services/api';

export default function PropertySwitcher({
  value,                  // { scope, brand_id, hotel_id, brand_name, hotel_name } | null
  onChange,
  source = 'public',      // 'public' | 'admin' — picks which endpoint to hit
  readOnly = false,
  placeholder = 'Search brand or hotel…',
}) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);
  const wrapRef = useRef(null);

  // Click-outside close
  useEffect(() => {
    const onDoc = (e) => {
      if (!wrapRef.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  // Debounced search
  useEffect(() => {
    if (!open || readOnly) return;
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const path = source === 'admin' ? '/admin/scope-search' : '/hotels/scope-search';
        const r = await api.get(path, { params: { q, limit: 20 } });
        setResults(r.data?.results || []);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 180);
    return () => clearTimeout(t);
  }, [q, open, source, readOnly]);

  const pick = (row) => {
    if (row.type === 'brand') {
      onChange?.({
        scope: 'brand',
        brand_id: row.id,
        brand_name: row.label,
      });
    } else {
      onChange?.({
        scope: 'hotel',
        hotel_id: row.id,
        brand_id: row.brand_id,
        brand_name: row.brand_name,
        hotel_name: row.label,
      });
    }
    setOpen(false);
    setQ('');
  };

  return (
    <div className="em-switcher" ref={wrapRef}>
      <input
        ref={inputRef}
        readOnly={readOnly}
        value={
          q !== ''
            ? q
            : value?.scope === 'hotel'
            ? `${value.brand_name || ''} · ${value.hotel_name || ''}`.trim()
            : value?.scope === 'brand'
            ? `${value.brand_name || ''} (brand)`
            : ''
        }
        placeholder={placeholder}
        onFocus={() => !readOnly && setOpen(true)}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
      />

      {value && (
        <div className="em-selection-chips">
          {value.scope === 'brand' && (
            <span className="em-chip brand-full">{value.brand_name} · all hotels</span>
          )}
          {value.scope === 'hotel' && (
            <>
              <span className="em-chip brand-half">{value.brand_name}</span>
              <span className="em-chip hotel-full">{value.hotel_name}</span>
            </>
          )}
        </div>
      )}

      {open && !readOnly && (
        <div className="em-switcher-results">
          {loading && <div style={{ padding: '8px 12px', fontSize: 12, color: 'var(--em-ink-soft)' }}>Searching…</div>}
          {!loading && results.length === 0 && (
            <div style={{ padding: '12px', fontSize: 12, color: 'var(--em-ink-soft)' }}>
              {q ? 'No brands or hotels match.' : 'Type to search…'}
            </div>
          )}
          {results.map((r) => (
            <div
              key={`${r.type}-${r.id}`}
              className={`em-switcher-row ${r.type}`}
              onMouseDown={(e) => { e.preventDefault(); pick(r); }}
            >
              {r.type === 'brand' ? (
                <>
                  <span className="em-hotel-name">{r.label}</span>
                  <span className="em-brand-tag">{r.hotel_count || 0} hotels</span>
                </>
              ) : (
                <>
                  <span className="em-brand-tag">{r.brand_name || ''}</span>
                  <span className="em-hotel-name">{r.label}</span>
                  {r.hotel_code && <span className="em-brand-tag">· {r.hotel_code}</span>}
                </>
              )}
              <span className="em-type-badge">{r.type}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
