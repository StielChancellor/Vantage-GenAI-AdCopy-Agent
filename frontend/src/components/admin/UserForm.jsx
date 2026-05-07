/**
 * UserForm — admin-only 5-tier user creation form (v2.2).
 *
 * Roles: admin | brand_manager | area_manager | hotel_marketing_manager | agency
 * Each role gates the assignment scope:
 *   - admin: no assignments (has everything)
 *   - brand_manager: brand-only multi-select
 *   - area_manager: hotel-only multi-select
 *   - hotel_marketing_manager: exactly one hotel
 *   - agency: brand-only OR hotel-only (or both) multi-select
 */
import { useState } from 'react';
import toast from 'react-hot-toast';
import api from '../../services/api';
import PropertySwitcher from '../PropertySwitcher';

const ROLES = [
  { value: 'admin', label: 'Admin', desc: 'Full access — every brand, every hotel, training, and audit logs.' },
  { value: 'brand_manager', label: 'Brand Manager', desc: 'Brand-level access plus every hotel under that brand.' },
  { value: 'area_manager', label: 'Area Manager', desc: 'Multiple hotels (no brand-level access).' },
  { value: 'hotel_marketing_manager', label: 'Hotel Marketing Manager', desc: 'Exactly one hotel.' },
  { value: 'agency', label: 'Agency', desc: 'Brands plus selected hotels — flexible client mix.' },
];

const SUPPORTS_BRAND = new Set(['brand_manager', 'agency']);
const SUPPORTS_HOTEL = new Set(['area_manager', 'agency', 'hotel_marketing_manager']);
const REQUIRES_SINGLE_HOTEL = new Set(['hotel_marketing_manager']);

export default function UserForm({ initial, onSaved, onCancel }) {
  const [fullName, setFullName] = useState(initial?.full_name || '');
  const [email, setEmail] = useState(initial?.email || '');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState(initial?.role || 'area_manager');
  const [showTokenCount, setShowTokenCount] = useState(!!initial?.show_token_count);
  const [showTokenAmount, setShowTokenAmount] = useState(!!initial?.show_token_amount);
  const [assignments, setAssignments] = useState(initial?.assignments || []);
  const [submitting, setSubmitting] = useState(false);

  const addAssignment = (sel) => {
    if (!sel) return;
    if (sel.scope === 'brand' && !SUPPORTS_BRAND.has(role)) {
      toast.error(`${role} cannot have brand-level access.`);
      return;
    }
    if (sel.scope === 'hotel' && !SUPPORTS_HOTEL.has(role)) {
      toast.error(`${role} cannot have hotel-level access.`);
      return;
    }
    if (REQUIRES_SINGLE_HOTEL.has(role) && assignments.length >= 1) {
      toast.error('Hotel Marketing Manager must have exactly 1 hotel.');
      return;
    }
    setAssignments([
      ...assignments,
      sel.scope === 'brand'
        ? { scope: 'brand', brand_id: sel.brand_id, _label: `${sel.brand_name} · all hotels` }
        : { scope: 'hotel', hotel_id: sel.hotel_id, _label: `${sel.brand_name} · ${sel.hotel_name}` },
    ]);
  };

  const removeAssignment = (idx) => {
    setAssignments(assignments.filter((_, i) => i !== idx));
  };

  const submit = async () => {
    if (!fullName || !email || (!initial && !password)) {
      toast.error('Full name, email, and password are required.');
      return;
    }
    if (REQUIRES_SINGLE_HOTEL.has(role) && assignments.length !== 1) {
      toast.error('Hotel Marketing Manager must have exactly 1 hotel.');
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
        assignments: assignments.map(({ _label, ...a }) => a),
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
              onClick={() => {
                setRole(r.value);
                // clear assignments incompatible with the new role
                if (r.value === 'admin') setAssignments([]);
                else if (REQUIRES_SINGLE_HOTEL.has(r.value)) setAssignments(assignments.slice(0, 1).filter((a) => a.scope === 'hotel'));
                else if (!SUPPORTS_BRAND.has(r.value)) setAssignments(assignments.filter((a) => a.scope !== 'brand'));
                else if (!SUPPORTS_HOTEL.has(r.value)) setAssignments(assignments.filter((a) => a.scope !== 'hotel'));
              }}
            >
              <div className="t">{r.label}</div>
              <div className="s" style={{ marginTop: 4, fontFamily: 'inherit', textTransform: 'none', letterSpacing: 0, color: 'var(--em-ink-soft)', fontSize: 11.5 }}>
                {r.desc}
              </div>
            </button>
          ))}
        </div>
      </div>

      {role !== 'admin' && (
        <div>
          <div className="em-mono-label" style={{ marginBottom: 8 }}>
            Assigned brands & hotels
          </div>
          <PropertySwitcher
            source="admin"
            value={null}
            onChange={(sel) => addAssignment(sel)}
            placeholder={
              REQUIRES_SINGLE_HOTEL.has(role)
                ? 'Search and select the one hotel this manager owns…'
                : 'Search and add a brand or hotel — repeat to assign multiple…'
            }
          />
          <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {assignments.length === 0 && (
              <span style={{ fontSize: 12, color: 'var(--em-ink-soft)' }}>No assignments yet.</span>
            )}
            {assignments.map((a, idx) => (
              <span
                key={idx}
                className={`em-chip ${a.scope === 'brand' ? 'brand-full' : 'hotel-full'}`}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '4px 10px', borderRadius: 999, fontSize: 12,
                  background: a.scope === 'brand' ? 'var(--em-accent)' : 'var(--em-ink)',
                  color: '#fff',
                }}
              >
                {a._label}
                <button
                  type="button"
                  onClick={() => removeAssignment(idx)}
                  style={{ background: 'transparent', border: 'none', color: '#fff', cursor: 'pointer', padding: 0, marginLeft: 4 }}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
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
        <button type="button" onClick={submit} disabled={submitting} className="btn-primary">
          {submitting ? 'Saving…' : initial ? 'Save changes' : 'Create user'}
        </button>
      </div>
    </div>
  );
}
