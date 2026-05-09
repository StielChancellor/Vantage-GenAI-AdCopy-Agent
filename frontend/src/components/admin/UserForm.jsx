/**
 * UserForm — admin-only user creation form (v2.4).
 *
 * Roles: admin | brand_manager | area_manager | hotel_marketing_manager | agency
 *
 * v2.4 — five "grant presets" replace the ad-hoc assignment list:
 *   1. Brand only          → [{scope:'brand', brand_id, brand_only:true}]
 *   2. All hotels in brand → [{scope:'brand', brand_id, brand_only:false}]
 *   3. Brand + few hotels  → [{scope:'brand', brand_id}, {scope:'hotel', hotel_id}, …]
 *   4. Club ITC only       → [{scope:'brand', brand_id:'club-itc'}]
 *   5. Complete group      → [{scope:'group'}]
 *
 * Plus a separate City scope add-on (multi-chip) usable with presets 1–4.
 */
import { useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import api, { getCities } from '../../services/api';
import PropertySwitcher from '../PropertySwitcher';
import { Sparkles } from 'lucide-react';

const ROLES = [
  { value: 'admin', label: 'Admin', desc: 'Full access — every brand, every hotel, training, and audit logs.' },
  { value: 'brand_manager', label: 'Brand Manager', desc: 'Brand-level access plus every hotel under that brand.' },
  { value: 'area_manager', label: 'Area Manager', desc: 'Multiple hotels (no brand-level access).' },
  { value: 'hotel_marketing_manager', label: 'Hotel Marketing Manager', desc: 'Exactly one hotel.' },
  { value: 'agency', label: 'Agency', desc: 'Brands plus selected hotels — flexible client mix.' },
];

const PRESETS = [
  { value: 'brand_only',     label: 'Brand only',          desc: 'Brand-level ad copy only — no per-hotel access.' },
  { value: 'brand_all',      label: 'All hotels in brand', desc: 'Brand + every hotel under it.' },
  { value: 'brand_select',   label: 'Brand + few hotels',  desc: 'Brand + a hand-picked subset of hotels.' },
  { value: 'club_itc',       label: 'Club ITC only',       desc: 'Loyalty programme — cross-chain anonymised exemplars.' },
  { value: 'group',          label: 'Complete group',      desc: 'Everything — Club ITC + every brand + every hotel.' },
  { value: 'hotels_only',    label: 'Hotels only',         desc: 'Pick one or more hotels directly (no brand access).' },
];

// Which presets each role may pick.
const PRESETS_BY_ROLE = {
  admin: [],
  brand_manager: ['brand_only', 'brand_all', 'brand_select', 'club_itc', 'group'],
  area_manager: ['hotels_only'],
  hotel_marketing_manager: ['hotels_only'],   // forced single hotel below
  agency: ['brand_only', 'brand_all', 'brand_select', 'club_itc', 'group', 'hotels_only'],
};

const CLUB_ITC_ID = 'club-itc';

export default function UserForm({ initial, onSaved, onCancel }) {
  const [fullName, setFullName] = useState(initial?.full_name || '');
  const [email, setEmail] = useState(initial?.email || '');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState(initial?.role || 'area_manager');
  const [showTokenCount, setShowTokenCount] = useState(!!initial?.show_token_count);
  const [showTokenAmount, setShowTokenAmount] = useState(!!initial?.show_token_amount);

  const [preset, setPreset] = useState('hotels_only');
  // For brand-flavoured presets: { brand_id, brand_name }
  const [presetBrand, setPresetBrand] = useState(null);
  // For 'brand_select': extra picked hotels [{hotel_id, hotel_name, brand_name}]
  const [extraHotels, setExtraHotels] = useState([]);
  // For 'hotels_only': picked hotels [{hotel_id, hotel_name, brand_name}]
  const [hotels, setHotels] = useState([]);
  // For city add-on: list of city strings
  const [cities, setCities] = useState([]);
  const [allCities, setAllCities] = useState([]);
  const [submitting, setSubmitting] = useState(false);

  // Reset incompatible preset whenever the role changes.
  useEffect(() => {
    const allowed = PRESETS_BY_ROLE[role] || [];
    if (allowed.length === 0) {
      setPreset('');
    } else if (!allowed.includes(preset)) {
      setPreset(allowed[0]);
    }
    if (role === 'hotel_marketing_manager') setHotels((h) => h.slice(0, 1));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role]);

  // Load city list once for the add-on chips.
  useEffect(() => {
    (async () => {
      try {
        const r = await getCities();
        setAllCities(r.data?.cities || []);
      } catch {/* ignore */}
    })();
  }, []);

  const allowedPresets = PRESETS_BY_ROLE[role] || [];
  const presetVisible = role !== 'admin' && allowedPresets.length > 0;
  const isLoyaltyPreset = preset === 'club_itc';
  const isGroupPreset = preset === 'group';
  const isBrandFlavour = ['brand_only', 'brand_all', 'brand_select'].includes(preset);
  const isHotelsOnly = preset === 'hotels_only';

  // City add-on is allowed for every preset except group (which already covers everything).
  const cityAddOnVisible = role !== 'admin' && !isGroupPreset && (role === 'brand_manager' || role === 'area_manager' || role === 'agency');

  const addExtraHotel = (sel) => {
    if (sel?.scope !== 'hotel') return;
    if (extraHotels.find((h) => h.hotel_id === sel.hotel_id)) return;
    setExtraHotels([...extraHotels, sel]);
  };
  const addHotel = (sel) => {
    if (sel?.scope !== 'hotel') return;
    if (role === 'hotel_marketing_manager' && hotels.length >= 1) {
      toast.error('Hotel Marketing Manager must have exactly one hotel.');
      return;
    }
    if (hotels.find((h) => h.hotel_id === sel.hotel_id)) return;
    setHotels([...hotels, sel]);
  };
  const toggleCity = (c) => {
    setCities((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));
  };

  // Compute the assignments payload from the preset state.
  const assignments = useMemo(() => {
    const out = [];
    if (isGroupPreset) {
      out.push({ scope: 'group' });
      return out;   // city add-on is suppressed for group
    }
    if (preset === 'brand_only' && presetBrand?.brand_id) {
      out.push({ scope: 'brand', brand_id: presetBrand.brand_id, brand_only: true });
    }
    if (preset === 'brand_all' && presetBrand?.brand_id) {
      out.push({ scope: 'brand', brand_id: presetBrand.brand_id, brand_only: false });
    }
    if (preset === 'brand_select' && presetBrand?.brand_id) {
      out.push({ scope: 'brand', brand_id: presetBrand.brand_id, brand_only: false });
      for (const h of extraHotels) out.push({ scope: 'hotel', hotel_id: h.hotel_id });
    }
    if (preset === 'club_itc') {
      out.push({ scope: 'brand', brand_id: CLUB_ITC_ID, brand_only: false });
    }
    if (preset === 'hotels_only') {
      for (const h of hotels) out.push({ scope: 'hotel', hotel_id: h.hotel_id });
    }
    for (const c of cities) out.push({ scope: 'city', city: c });
    return out;
  }, [preset, presetBrand, extraHotels, hotels, cities, isGroupPreset]);

  const submit = async () => {
    if (!fullName || !email || (!initial && !password)) {
      toast.error('Full name, email, and password are required.');
      return;
    }
    if (role === 'hotel_marketing_manager' && hotels.length !== 1) {
      toast.error('Hotel Marketing Manager must have exactly 1 hotel.');
      return;
    }
    if (role !== 'admin' && assignments.length === 0) {
      toast.error('Pick a grant preset (and complete its required fields) before saving.');
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        full_name: fullName,
        email,
        role,
        show_token_count: showTokenCount,
        show_token_amount: showTokenAmount,
        assignments,
        ...(password ? { password } : {}),
      };
      if (initial?.uid) {
        await api.put(`/admin/users/${initial.uid}`, payload);
        toast.success('User updated.');
      } else {
        await api.post('/admin/users', payload);
        toast.success('User created.');
      }
      onSaved?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Save failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="em-card" style={{ display: 'grid', gap: 18 }}>
      <h3 className="em-display" style={{ margin: 0, fontSize: 22 }}>
        {initial ? 'Edit user' : <>Create <em>user</em></>}
      </h3>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <label>
          <div className="em-mono-label">Full name</div>
          <input value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </label>
        <label>
          <div className="em-mono-label">Email</div>
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" />
        </label>
      </div>

      <label>
        <div className="em-mono-label">Password{initial ? ' (leave blank to keep)' : ''}</div>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      </label>

      <div>
        <div className="em-mono-label" style={{ marginBottom: 8 }}>Role</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
          {ROLES.map((r) => (
            <button
              key={r.value}
              type="button"
              className="em-mode-card"
              aria-selected={role === r.value}
              onClick={() => setRole(r.value)}
            >
              <div className="t">{r.label}</div>
              <div className="s" style={{ marginTop: 4, fontFamily: 'inherit', textTransform: 'none', letterSpacing: 0, color: 'var(--em-ink-soft)', fontSize: 11.5 }}>
                {r.desc}
              </div>
            </button>
          ))}
        </div>
      </div>

      {presetVisible && (
        <div>
          <div className="em-mono-label" style={{ marginBottom: 8 }}>Access preset</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 8 }}>
            {PRESETS.filter((p) => allowedPresets.includes(p.value)).map((p) => (
              <button
                key={p.value}
                type="button"
                className="em-mode-card"
                aria-selected={preset === p.value}
                onClick={() => setPreset(p.value)}
              >
                <div className="t" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  {p.value === 'club_itc' && <Sparkles size={13} style={{ color: 'var(--em-accent)' }} />}
                  {p.label}
                </div>
                <div className="s" style={{ marginTop: 4, fontFamily: 'inherit', textTransform: 'none', letterSpacing: 0, color: 'var(--em-ink-soft)', fontSize: 11.5 }}>
                  {p.desc}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Brand picker for brand-flavoured presets */}
      {role !== 'admin' && isBrandFlavour && (
        <div>
          <div className="em-mono-label" style={{ marginBottom: 6 }}>Brand</div>
          {presetBrand ? (
            <span className="em-chip brand-full" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 10px', borderRadius: 999, background: 'var(--em-accent)', color: '#fff', fontSize: 12 }}>
              {presetBrand.brand_name}
              <button type="button" onClick={() => { setPresetBrand(null); setExtraHotels([]); }} style={{ background: 'transparent', border: 'none', color: '#fff', cursor: 'pointer' }}>×</button>
            </span>
          ) : (
            <PropertySwitcher
              source="admin"
              value={null}
              onChange={(sel) => { if (sel?.scope === 'brand') setPresetBrand({ brand_id: sel.brand_id, brand_name: sel.brand_name }); }}
              placeholder="Search and pick a brand…"
            />
          )}
        </div>
      )}

      {/* Hotel sub-picker for brand_select preset */}
      {role !== 'admin' && preset === 'brand_select' && presetBrand && (
        <div>
          <div className="em-mono-label" style={{ marginBottom: 6 }}>Extra hotels (optional)</div>
          <PropertySwitcher
            source="admin"
            value={null}
            onChange={(sel) => addExtraHotel(sel)}
            placeholder={`Add specific hotels under ${presetBrand.brand_name} or any brand…`}
          />
          <div style={{ marginTop: 6, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {extraHotels.map((h, idx) => (
              <span key={idx} className="em-chip hotel-full" style={{ padding: '4px 10px', borderRadius: 999, background: 'var(--em-ink)', color: '#fff', fontSize: 12 }}>
                {h.brand_name} · {h.hotel_name}
                <button type="button" onClick={() => setExtraHotels(extraHotels.filter((_, i) => i !== idx))} style={{ background: 'transparent', border: 'none', color: '#fff', marginLeft: 4, cursor: 'pointer' }}>×</button>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Hotels-only picker */}
      {role !== 'admin' && isHotelsOnly && (
        <div>
          <div className="em-mono-label" style={{ marginBottom: 6 }}>Hotels</div>
          <PropertySwitcher
            source="admin"
            value={null}
            onChange={(sel) => addHotel(sel)}
            placeholder={role === 'hotel_marketing_manager' ? 'Pick the single hotel this user owns…' : 'Add hotels — repeat to assign multiple…'}
          />
          <div style={{ marginTop: 6, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {hotels.map((h, idx) => (
              <span key={idx} className="em-chip hotel-full" style={{ padding: '4px 10px', borderRadius: 999, background: 'var(--em-ink)', color: '#fff', fontSize: 12 }}>
                {h.brand_name} · {h.hotel_name}
                <button type="button" onClick={() => setHotels(hotels.filter((_, i) => i !== idx))} style={{ background: 'transparent', border: 'none', color: '#fff', marginLeft: 4, cursor: 'pointer' }}>×</button>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* City add-on chips */}
      {cityAddOnVisible && (
        <div>
          <div className="em-mono-label" style={{ marginBottom: 6 }}>Cities (optional add-on)</div>
          {allCities.length === 0 ? (
            <div style={{ fontSize: 12, color: 'var(--em-ink-soft)' }}>
              No cities available — ingest hotels with a `city` column to populate this list.
            </div>
          ) : (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {allCities.map((c) => (
                <button
                  key={c.city}
                  type="button"
                  className="em-chip"
                  aria-pressed={cities.includes(c.city)}
                  onClick={() => toggleCity(c.city)}
                  style={{
                    padding: '4px 10px', borderRadius: 999, fontSize: 12, cursor: 'pointer',
                    background: cities.includes(c.city) ? 'var(--em-accent)' : 'var(--em-surface-2)',
                    color: cities.includes(c.city) ? '#fff' : 'var(--em-ink)',
                    border: '1px solid var(--em-line)',
                  }}
                >
                  {c.city} · {c.hotel_count}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div style={{ display: 'grid', gap: 6 }}>
        <div className="em-mono-label">Visibility</div>
        <label style={{ fontSize: 13 }}>
          <input type="checkbox" checked={showTokenCount} onChange={(e) => setShowTokenCount(e.target.checked)} />
          {' '}Show this user their token consumption
        </label>
        <label style={{ fontSize: 13 }}>
          <input type="checkbox" checked={showTokenAmount} onChange={(e) => setShowTokenAmount(e.target.checked)} />
          {' '}Show this user the rupee amount of their token consumption
        </label>
      </div>

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        {onCancel && <button type="button" onClick={onCancel} disabled={submitting}>Cancel</button>}
        <button type="button" onClick={submit} disabled={submitting} className="btn btn-primary">
          {submitting ? 'Saving…' : initial ? 'Save changes' : 'Create user'}
        </button>
      </div>
    </div>
  );
}
