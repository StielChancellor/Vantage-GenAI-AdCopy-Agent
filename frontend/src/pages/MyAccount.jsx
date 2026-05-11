/**
 * MyAccount — Profile + Properties + Billing (v2.2).
 * Token consumption columns are gated by the user's show_token_count /
 * show_token_amount flags (set by admin). Server returns null for redacted
 * fields; we render "—" in their place.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api, { listCampaigns, archiveCampaign, unlockCampaign } from '../services/api';
import { APP_VERSION, APP_VERSION_DATE } from '../version';
import toast from 'react-hot-toast';

export default function MyAccount() {
  const navigate = useNavigate();
  const [me, setMe] = useState(null);
  const [billing, setBilling] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errMsg, setErrMsg] = useState('');
  const [tab, setTab] = useState('profile');
  const [campaigns, setCampaigns] = useState([]);
  const [campaignsLoading, setCampaignsLoading] = useState(false);

  const loadCampaigns = async () => {
    setCampaignsLoading(true);
    try {
      const r = await listCampaigns({ limit: 100 });
      setCampaigns(r.data || []);
    } catch {
      setCampaigns([]);
    } finally {
      setCampaignsLoading(false);
    }
  };
  useEffect(() => {
    if (tab === 'unified-briefs') loadCampaigns();
  }, [tab]);

  const editCampaign = async (c) => {
    try {
      if (c.status === 'locked') await unlockCampaign(c.id);
      navigate(`/unified?campaign=${encodeURIComponent(c.id)}`);
    } catch {
      toast.error('Could not open campaign for edit.');
    }
  };
  const doArchive = async (c) => {
    if (!window.confirm(`Archive "${c.structured?.campaign_name || 'this campaign'}"?`)) return;
    try {
      await archiveCampaign(c.id);
      toast.success('Archived.');
      loadCampaigns();
    } catch {
      toast.error('Archive failed.');
    }
  };

  useEffect(() => {
    (async () => {
      // Use allSettled so one failure doesn't kill the whole page.
      const [meR, billR] = await Promise.allSettled([
        api.get('/auth/me'),
        api.get('/auth/me/billing'),
      ]);
      if (meR.status === 'fulfilled') {
        setMe(meR.value.data);
      } else {
        setErrMsg(meR.reason?.response?.data?.detail || meR.reason?.message || 'Failed to load profile');
      }
      if (billR.status === 'fulfilled') {
        setBilling(billR.value.data);
      } else {
        // Billing failure is non-fatal — show empty billing.
        setBilling({ show_token_count: false, show_token_amount: false, total_tokens: null, total_cost_inr: null, rows: [] });
      }
      setLoading(false);
    })();
  }, []);

  if (loading) return <div className="em-card">Loading…</div>;
  if (!me) return (
    <div className="em-card">
      <div className="em-mono-label">Profile</div>
      <p style={{ marginTop: 6 }}>Could not load profile.</p>
      {errMsg && <p style={{ fontSize: 12, color: 'var(--em-ink-soft)', marginTop: 4 }}>{errMsg}</p>}
    </div>
  );

  return (
    <div style={{ display: 'grid', gap: 18 }}>
      <div>
        <h2 className="em-display" style={{ margin: 0, fontSize: 32 }}>
          My <em>Account</em>
        </h2>
        <p style={{ color: 'var(--em-ink-soft)', margin: '4px 0 0', fontSize: 13 }}>
          Profile, properties, and billing — all in one place. App v{APP_VERSION} · {APP_VERSION_DATE}
        </p>
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {[
          ['profile', 'Profile'],
          ['properties', 'Properties & brands'],
          ['billing', 'Billing & usage'],
          ['unified-briefs', 'Unified Briefs'],
        ].map(([k, label]) => (
          <button key={k} type="button" className="em-mode-card" aria-selected={tab === k} onClick={() => setTab(k)}>
            <div className="t">{label}</div>
          </button>
        ))}
      </div>

      {tab === 'profile' && (
        <div className="em-card" style={{ display: 'grid', gap: 12 }}>
          <div className="em-mono-label">Account</div>
          <div style={{ fontSize: 18, fontWeight: 600 }}>{me.full_name}</div>
          <div style={{ color: 'var(--em-ink-soft)', fontSize: 13 }}>
            {me.email} · <span className="em-pill accent">{me.role.replace('_', ' ')}</span>
          </div>
          <div className="em-mono-label" style={{ marginTop: 8 }}>Visibility (set by admin)</div>
          <div style={{ fontSize: 13 }}>
            Token consumption: <strong>{me.show_token_count ? 'visible' : 'hidden'}</strong>
            {' · '}
            Token cost (₹): <strong>{me.show_token_amount ? 'visible' : 'hidden'}</strong>
          </div>
        </div>
      )}

      {tab === 'properties' && (
        <div className="em-card">
          <div className="em-mono-label">Your access</div>
          {me.scope_summary && (me.scope_summary.brand_count + me.scope_summary.hotel_count > 0) ? (
            <>
              <div style={{ fontSize: 14, marginTop: 6 }}>
                <strong>{me.scope_summary.brand_count}</strong> brand{me.scope_summary.brand_count !== 1 ? 's' : ''} ·{' '}
                <strong>{me.scope_summary.hotel_count}</strong> hotel{me.scope_summary.hotel_count !== 1 ? 's' : ''}
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
                {me.scope_summary.brand_names.map((b) => (
                  <span key={b} className="em-pill accent">{b}</span>
                ))}
                {me.scope_summary.hotel_names.map((h) => (
                  <span key={h} className="em-pill">{h}</span>
                ))}
              </div>
            </>
          ) : (
            <p style={{ fontSize: 13, color: 'var(--em-ink-soft)' }}>
              {me.role === 'admin' ? 'Admins have access to every brand and hotel.' : 'No properties assigned. Ask your admin to grant access.'}
            </p>
          )}
          <p style={{ fontSize: 12, color: 'var(--em-ink-faint)', marginTop: 14 }}>
            New properties and brands are created by admins via <strong>Admin → Hotels Ingestion</strong>.
          </p>
        </div>
      )}

      {tab === 'billing' && billing && (
        <div className="em-card">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10, marginBottom: 14 }}>
            <Stat
              label="Total tokens"
              value={billing.total_tokens != null ? billing.total_tokens.toLocaleString() : '—'}
              redacted={billing.total_tokens == null}
            />
            <Stat
              label="Total cost (₹)"
              value={billing.total_cost_inr != null ? `₹${billing.total_cost_inr.toFixed(4)}` : '—'}
              redacted={billing.total_cost_inr == null}
            />
          </div>

          {!billing.show_token_count && !billing.show_token_amount && (
            <div className="em-pill muted" style={{ marginBottom: 12 }}>
              Token visibility is disabled for your account by your admin.
            </div>
          )}

          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--em-line)', textAlign: 'left' }}>
                <th className="em-mono-label">When</th>
                <th className="em-mono-label">Hotel</th>
                <th className="em-mono-label">Offer</th>
                <th className="em-mono-label">Tokens</th>
                <th className="em-mono-label">Cost (₹)</th>
                <th className="em-mono-label">Generation ID</th>
              </tr>
            </thead>
            <tbody>
              {billing.rows.map((r) => (
                <tr key={r.id} style={{ borderBottom: '1px solid var(--em-line)' }}>
                  <td style={{ padding: '6px 4px' }}>{(r.timestamp || '').slice(0, 10)}</td>
                  <td>{r.hotel_name}</td>
                  <td style={{ color: 'var(--em-ink-soft)' }}>{r.offer_name}</td>
                  <td className={r.tokens == null ? 'em-redacted' : ''}>
                    {r.tokens != null ? r.tokens.toLocaleString() : '—'}
                  </td>
                  <td className={r.cost_inr == null ? 'em-redacted' : ''}>
                    {r.cost_inr != null ? `₹${Number(r.cost_inr).toFixed(4)}` : '—'}
                  </td>
                  <td style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: 'var(--em-ink-soft)' }}>
                    {(r.generation_id || '').slice(0, 8) || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {billing.rows.length === 0 && (
            <p style={{ fontSize: 13, color: 'var(--em-ink-soft)', marginTop: 12 }}>No generations yet.</p>
          )}
        </div>
      )}

      {tab === 'unified-briefs' && (
        <div className="em-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
            <div>
              <div className="em-mono-label">Unified Briefs</div>
              <p style={{ fontSize: 13, color: 'var(--em-ink-soft)', marginTop: 4 }}>
                Locked campaigns are immutable until you unlock them. Editing a locked brief flips it back to draft.
              </p>
            </div>
            <button className="btn btn-primary" onClick={() => navigate('/unified')}>+ New campaign</button>
          </div>
          {campaignsLoading ? (
            <p style={{ fontSize: 13, color: 'var(--em-ink-soft)' }}>Loading…</p>
          ) : campaigns.length === 0 ? (
            <p style={{ fontSize: 13, color: 'var(--em-ink-soft)' }}>
              No campaigns yet — start one with the button above.
            </p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--em-line)', textAlign: 'left' }}>
                  <th className="em-mono-label">Name</th>
                  <th className="em-mono-label">Status</th>
                  <th className="em-mono-label">Dates</th>
                  <th className="em-mono-label">Generations</th>
                  <th className="em-mono-label">Last edited</th>
                  <th className="em-mono-label"></th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr key={c.id} style={{ borderBottom: '1px solid var(--em-line)' }}>
                    <td style={{ padding: '6px 4px', fontWeight: 600 }}>
                      {c.structured?.campaign_name || '(untitled)'}
                    </td>
                    <td>
                      <span className={`em-pill ${c.status === 'locked' ? 'accent' : c.status === 'archived' ? 'muted' : ''}`}>
                        {c.status}
                      </span>
                    </td>
                    <td style={{ color: 'var(--em-ink-soft)' }}>
                      {(c.structured?.start_date || '—')} → {(c.structured?.end_date || '—')}
                    </td>
                    <td>{(c.generated || []).length}</td>
                    <td style={{ color: 'var(--em-ink-soft)' }}>{(c.updated_at || '').slice(0, 10)}</td>
                    <td style={{ display: 'flex', gap: 6, padding: '6px 4px' }}>
                      <button className="btn btn-sm btn-outline" onClick={() => editCampaign(c)}>Edit</button>
                      {c.status !== 'archived' && (
                        <button className="btn btn-sm btn-outline" onClick={() => doArchive(c)}>Archive</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, redacted }) {
  return (
    <div style={{ padding: 12, borderRadius: 10, background: 'var(--em-surface-2)', border: '1px solid var(--em-line)' }}>
      <div className="em-display" style={{ fontSize: 24, lineHeight: 1, color: redacted ? 'var(--em-ink-faint)' : 'var(--em-ink)' }}>
        {value}
      </div>
      <div className="em-mono-label" style={{ marginTop: 6 }}>{label}</div>
    </div>
  );
}
