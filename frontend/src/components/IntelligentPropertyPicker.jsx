/**
 * IntelligentPropertyPicker — role-aware property/brand/city picker (v2.4).
 *
 * Behaviour driven by the user's scope_summary returned from /auth/me:
 *
 *   • Exactly 1 hotel, no brands → static chip showing that hotel. No picker.
 *   • 1 brand, no hotels         → brand chip; expand to narrow to a single hotel.
 *   • Multiple hotels, no brands → typing-space; click opens a checkbox dropdown
 *     of every accessible hotel. Multi-select.
 *   • Multiple brands or mixed   → typing-space; type fires /hotels/scope-search.
 *     Dropdown shows Club ITC at top with 'Loyalty' badge, then matching cities,
 *     brands, and hotels. All checkboxes are independent — user can mix.
 *
 * Emits a single `selection` object up:
 *   {
 *     scope: 'hotel' | 'brand' | 'city' | 'multi' | 'loyalty',
 *     hotel_ids: [...], brand_ids: [...], cities: [...],
 *     hotel_id?: '', brand_id?: '',
 *     is_loyalty: bool,
 *     // Display helpers (denormed, never sent to backend):
 *     _labels: { hotels: [{id,label,brand}], brands: [{id,label,kind}], cities: [{id,label}] }
 *   }
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { Sparkles, X, Search } from 'lucide-react';
import { scopeSearch } from '../services/api';

const EMPTY_SELECTION = {
  scope: 'hotel',
  hotel_ids: [],
  brand_ids: [],
  cities: [],
  is_loyalty: false,
  _labels: { hotels: [], brands: [], cities: [] },
};

function deriveScope(sel) {
  // Pick the most specific scope based on what's selected.
  const { hotel_ids = [], brand_ids = [], cities = [] } = sel;
  const totalKinds = (hotel_ids.length > 0 ? 1 : 0) + (brand_ids.length > 0 ? 1 : 0) + (cities.length > 0 ? 1 : 0);
  if (totalKinds === 0) return 'hotel';
  if (totalKinds > 1) return 'multi';
  if (hotel_ids.length === 1 && brand_ids.length === 0 && cities.length === 0) return 'hotel';
  if (hotel_ids.length > 1) return 'multi';
  if (brand_ids.length === 1 && hotel_ids.length === 0 && cities.length === 0) return sel.is_loyalty ? 'loyalty' : 'brand';
  if (brand_ids.length > 1) return 'multi';
  if (cities.length >= 1 && hotel_ids.length === 0 && brand_ids.length === 0) return 'city';
  return 'multi';
}

export default function IntelligentPropertyPicker({
  value,                       // selection object or null
  onChange,
  scopeSummary,                // from /auth/me (counts + has_loyalty + has_group)
  placeholder,
}) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const wrapRef = useRef(null);
  const inputRef = useRef(null);

  // Local copy used while editing.
  const sel = value || EMPTY_SELECTION;

  // Click-outside close.
  useEffect(() => {
    const onDoc = (e) => {
      if (!wrapRef.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  // Auto-pick the single accessible entity if the user truly has only one.
  // (scopeSummary.hotel_count === 1 && brand_count === 0 → static chip mode.)
  // We push the selection up the first time scopeSummary lands.
  useEffect(() => {
    if (!scopeSummary) return;
    const totalDirect =
      (scopeSummary.hotel_count || 0) +
      (scopeSummary.brand_count || 0) +
      (scopeSummary.city_count || 0);
    if (totalDirect !== 1) return;
    if (sel._auto) return;
    // We don't have IDs in scope_summary; do a single empty scope-search to grab them.
    (async () => {
      try {
        const r = await scopeSearch({ includeEmpty: true, limit: 5 });
        const rows = r.data?.results || [];
        if (rows.length === 1) {
          const row = rows[0];
          if (row.type === 'hotel') {
            const next = {
              ...EMPTY_SELECTION,
              hotel_ids: [row.id],
              brand_ids: row.brand_id ? [row.brand_id] : [],
              _labels: {
                hotels: [{ id: row.id, label: row.label, brand: row.brand_name }],
                brands: [],
                cities: [],
              },
              _auto: true,
            };
            next.scope = deriveScope(next);
            onChange?.(next);
          } else if (row.type === 'brand') {
            const isLoyalty = row.kind === 'loyalty';
            const next = {
              ...EMPTY_SELECTION,
              brand_ids: [row.id],
              is_loyalty: isLoyalty,
              _labels: {
                hotels: [],
                brands: [{ id: row.id, label: row.label, kind: row.kind }],
                cities: [],
              },
              _auto: true,
            };
            next.scope = deriveScope(next);
            onChange?.(next);
          }
        }
      } catch {/* best-effort */}
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeSummary?.hotel_count, scopeSummary?.brand_count, scopeSummary?.city_count]);

  // Debounced search whenever the dropdown is open.
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await scopeSearch({ q, includeEmpty: !q, limit: 30 });
        setResults(r.data?.results || []);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 160);
    return () => clearTimeout(t);
  }, [q, open]);

  const isStaticHotel =
    (scopeSummary?.hotel_count || 0) === 1 &&
    (scopeSummary?.brand_count || 0) === 0 &&
    (scopeSummary?.city_count || 0) === 0 &&
    !scopeSummary?.has_group;

  const placeholderText =
    placeholder ||
    (isStaticHotel
      ? 'Property locked to your account'
      : (scopeSummary?.has_loyalty ? 'Type Club ITC, brand, or hotel…' : 'Type brand or hotel…'));

  // Selection toggling helpers.
  const toggle = (row) => {
    const next = { ...sel, _auto: false };
    next.hotel_ids = [...(sel.hotel_ids || [])];
    next.brand_ids = [...(sel.brand_ids || [])];
    next.cities = [...(sel.cities || [])];
    next._labels = {
      hotels: [...(sel._labels?.hotels || [])],
      brands: [...(sel._labels?.brands || [])],
      cities: [...(sel._labels?.cities || [])],
    };
    if (row.type === 'hotel') {
      const i = next.hotel_ids.indexOf(row.id);
      if (i === -1) {
        next.hotel_ids.push(row.id);
        next._labels.hotels.push({ id: row.id, label: row.label, brand: row.brand_name });
      } else {
        next.hotel_ids.splice(i, 1);
        next._labels.hotels = next._labels.hotels.filter((h) => h.id !== row.id);
      }
    } else if (row.type === 'brand') {
      const i = next.brand_ids.indexOf(row.id);
      if (i === -1) {
        next.brand_ids.push(row.id);
        next._labels.brands.push({ id: row.id, label: row.label, kind: row.kind });
        if (row.kind === 'loyalty') next.is_loyalty = true;
      } else {
        next.brand_ids.splice(i, 1);
        next._labels.brands = next._labels.brands.filter((b) => b.id !== row.id);
        next.is_loyalty = next._labels.brands.some((b) => b.kind === 'loyalty');
      }
    } else if (row.type === 'city') {
      const i = next.cities.indexOf(row.label);
      if (i === -1) {
        next.cities.push(row.label);
        next._labels.cities.push({ id: row.id, label: row.label });
      } else {
        next.cities.splice(i, 1);
        next._labels.cities = next._labels.cities.filter((c) => c.label !== row.label);
      }
    }
    next.scope = deriveScope(next);
    // Convenience denorm fields for legacy backend code (single-pick).
    next.hotel_id = next.hotel_ids[0] || '';
    next.brand_id = next.brand_ids[0] || (next._labels.hotels[0]?.brand_id || '');
    onChange?.(next);
  };

  const removeChip = (kind, id) => {
    const next = { ...sel, _auto: false };
    next.hotel_ids = [...(sel.hotel_ids || [])];
    next.brand_ids = [...(sel.brand_ids || [])];
    next.cities = [...(sel.cities || [])];
    next._labels = {
      hotels: [...(sel._labels?.hotels || [])],
      brands: [...(sel._labels?.brands || [])],
      cities: [...(sel._labels?.cities || [])],
    };
    if (kind === 'hotel') {
      next.hotel_ids = next.hotel_ids.filter((x) => x !== id);
      next._labels.hotels = next._labels.hotels.filter((h) => h.id !== id);
    } else if (kind === 'brand') {
      next.brand_ids = next.brand_ids.filter((x) => x !== id);
      next._labels.brands = next._labels.brands.filter((b) => b.id !== id);
      next.is_loyalty = next._labels.brands.some((b) => b.kind === 'loyalty');
    } else if (kind === 'city') {
      next.cities = next.cities.filter((x) => x !== id);
      next._labels.cities = next._labels.cities.filter((c) => c.label !== id);
    }
    next.scope = deriveScope(next);
    next.hotel_id = next.hotel_ids[0] || '';
    next.brand_id = next.brand_ids[0] || '';
    onChange?.(next);
  };

  const selectionEmpty =
    (sel.hotel_ids?.length || 0) +
      (sel.brand_ids?.length || 0) +
      (sel.cities?.length || 0) ===
    0;

  // Group results for nice ordering: loyalty brands first, then cities, then hotel brands, then hotels.
  // Also fold in any currently-selected rows that the latest search response omitted —
  // this keeps the dropdown showing what the user has chosen so they can deselect.
  const grouped = useMemo(() => {
    const out = { loyalty: [], cities: [], brands: [], hotels: [] };
    const seen = new Set();
    const push = (r) => {
      const key = `${r.type}:${r.id || r.label}`;
      if (seen.has(key)) return;
      seen.add(key);
      if (r.type === 'brand' && r.kind === 'loyalty') out.loyalty.push(r);
      else if (r.type === 'brand') out.brands.push(r);
      else if (r.type === 'city') out.cities.push(r);
      else if (r.type === 'hotel') out.hotels.push(r);
    };
    for (const r of results) push(r);
    // Fold selected rows back so they're visible even if the search filtered them out.
    for (const h of (sel._labels?.hotels || [])) {
      push({ type: 'hotel', id: h.id, label: h.label, brand_name: h.brand, city: '' });
    }
    for (const b of (sel._labels?.brands || [])) {
      push({ type: 'brand', id: b.id, label: b.label, kind: b.kind, hotel_count: 0 });
    }
    for (const c of (sel._labels?.cities || [])) {
      push({ type: 'city', id: c.id, label: c.label, hotel_count: 0 });
    }
    return out;
  }, [results, sel]);

  const isPicked = (row) => {
    if (row.type === 'hotel') return (sel.hotel_ids || []).includes(row.id);
    if (row.type === 'brand') return (sel.brand_ids || []).includes(row.id);
    if (row.type === 'city') return (sel.cities || []).includes(row.label);
    return false;
  };

  // Static-hotel mode: single chip, no input.
  if (isStaticHotel && (sel.hotel_ids?.length || 0) > 0) {
    const h = sel._labels?.hotels?.[0];
    return (
      <div className="em-switcher" ref={wrapRef}>
        <div className="em-selection-chips">
          {h?.brand && <span className="em-chip brand-half">{h.brand}</span>}
          <span className="em-chip hotel-full">{h?.label || 'Selected hotel'}</span>
          <span className="em-pill" style={{ marginLeft: 8 }}>locked</span>
        </div>
      </div>
    );
  }

  return (
    <div className="em-switcher" ref={wrapRef}>
      <div className="em-switcher-input-wrap" style={{ position: 'relative' }}>
        <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', opacity: 0.5 }} />
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          placeholder={placeholderText}
          style={{ paddingLeft: 30 }}
        />
      </div>

      {/* Selected-chip rail */}
      {!selectionEmpty && (
        <div className="em-selection-chips" style={{ marginTop: 8 }}>
          {sel._labels?.brands?.map((b) => (
            <span
              key={`bchip-${b.id}`}
              className={b.kind === 'loyalty' ? 'em-chip brand-full em-chip-loyalty' : 'em-chip brand-full'}
              style={b.kind === 'loyalty' ? { background: 'linear-gradient(135deg, var(--em-accent), var(--em-accent-ink, #7a1f10))' } : undefined}
            >
              {b.kind === 'loyalty' && <Sparkles size={11} style={{ marginRight: 4 }} />}
              {b.label}{b.kind === 'loyalty' ? ' · loyalty' : ' · all hotels'}
              <button type="button" className="em-chip-x" onClick={() => removeChip('brand', b.id)} aria-label="remove"><X size={11} /></button>
            </span>
          ))}
          {sel._labels?.cities?.map((c) => (
            <span key={`cchip-${c.label}`} className="em-chip">
              {c.label} (city)
              <button type="button" className="em-chip-x" onClick={() => removeChip('city', c.label)} aria-label="remove"><X size={11} /></button>
            </span>
          ))}
          {sel._labels?.hotels?.map((h) => (
            <span key={`hchip-${h.id}`} className="em-chip hotel-full">
              {h.brand ? `${h.brand} · ${h.label}` : h.label}
              <button type="button" className="em-chip-x" onClick={() => removeChip('hotel', h.id)} aria-label="remove"><X size={11} /></button>
            </span>
          ))}
        </div>
      )}

      {open && (
        <div className="em-switcher-results">
          {loading && <div style={{ padding: '8px 12px', fontSize: 12, color: 'var(--em-ink-soft)' }}>Searching…</div>}
          {!loading
            && results.length === 0
            && grouped.loyalty.length === 0
            && grouped.cities.length === 0
            && grouped.brands.length === 0
            && grouped.hotels.length === 0 && (
            <div style={{ padding: '12px', fontSize: 12, color: 'var(--em-ink-soft)' }}>
              {q ? 'No matches in your scope.' : 'Start typing to filter, or browse the list…'}
            </div>
          )}

          {grouped.loyalty.length > 0 && (
            <>
              <div className="em-switcher-section">Loyalty</div>
              {grouped.loyalty.map((r) => (
                <Row key={`l-${r.id}`} row={r} picked={isPicked(r)} onClick={() => toggle(r)} loyalty />
              ))}
            </>
          )}
          {grouped.cities.length > 0 && (
            <>
              <div className="em-switcher-section">Cities</div>
              {grouped.cities.map((r) => (
                <Row key={`c-${r.id}`} row={r} picked={isPicked(r)} onClick={() => toggle(r)} />
              ))}
            </>
          )}
          {grouped.brands.length > 0 && (
            <>
              <div className="em-switcher-section">Brands</div>
              {grouped.brands.map((r) => (
                <Row key={`b-${r.id}`} row={r} picked={isPicked(r)} onClick={() => toggle(r)} />
              ))}
            </>
          )}
          {grouped.hotels.length > 0 && (
            <>
              <div className="em-switcher-section">Hotels</div>
              {grouped.hotels.map((r) => (
                <Row key={`h-${r.id}`} row={r} picked={isPicked(r)} onClick={() => toggle(r)} />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ row, picked, onClick, loyalty }) {
  const label = row.label || row.id || '(unnamed)';
  return (
    <div
      className={`em-switcher-row ${row.type}${picked ? ' picked' : ''}`}
      onMouseDown={(e) => { e.preventDefault(); onClick(); }}
      role="checkbox"
      aria-checked={picked}
    >
      <input type="checkbox" checked={picked} readOnly tabIndex={-1} className="em-switcher-check" />
      {row.type === 'brand' ? (
        <>
          <span className="em-hotel-name">
            {loyalty && <Sparkles size={12} style={{ marginRight: 6, color: 'var(--em-accent)' }} />}
            {label}
          </span>
          <span className="em-brand-tag">{loyalty ? 'Loyalty programme' : `${row.hotel_count || 0} hotels`}</span>
        </>
      ) : row.type === 'city' ? (
        <>
          <span className="em-hotel-name">{label}</span>
          <span className="em-brand-tag">{row.hotel_count || 0} hotels</span>
        </>
      ) : (
        <>
          {row.brand_name && <span className="em-brand-tag">{row.brand_name}</span>}
          <span className="em-hotel-name">{label}</span>
          {row.city && <span className="em-brand-tag">· {row.city}</span>}
        </>
      )}
      <span className="em-type-badge">{row.type}</span>
    </div>
  );
}
