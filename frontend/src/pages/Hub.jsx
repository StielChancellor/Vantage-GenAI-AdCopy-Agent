/**
 * Hub Home — post-login landing (v2.3).
 *
 * Hi-fi recreation of the Vantage Hub Hi-Fi handoff:
 *   - hero greeting
 *   - identity strip with active workspace + chips
 *   - tools grid (Ad Copy, CRM, Unified, Calendar)
 *   - "pick up where you left off" recents pulled from /auth/me/billing
 *   - side panel with property memory + suggested next + this week stats
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Megaphone, Mail, Zap, Calendar, ArrowRight, MessageSquare, Plus, BookmarkCheck, X,
} from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../hooks/useAuth';
import { useSelection } from '../contexts/SelectionContext';
import IntelligentPropertyPicker from '../components/IntelligentPropertyPicker';

const TOOLS = [
  { id: 'ideation', num: '01 / Agent', icon: Zap, title: 'Campaign Ideation',
    blurb: 'Brief in. Concepts out. Iterate with a creative-director agent until you have ten polished names.',
    chip: 'Start here', to: '/ideation', featured: true },
  { id: 'unified', num: '02 / Agent', icon: Zap, title: 'Unified Campaign Copy',
    blurb: 'Take a chosen concept end-to-end: ads + CRM, fanned out across the chain.',
    chip: 'Brief → fan-out', to: '/unified' },
  { id: 'adcopy',  num: '03 / Agent', icon: Megaphone, title: 'Media Ad Copy',
    blurb: 'Headlines & descriptions across Google, Meta, YouTube — six platforms in one generation.',
    chip: '28 variants typical', to: '/adcopy' },
  { id: 'crm',     num: '04 / Agent', icon: Mail, title: 'CRM Copy',
    blurb: 'WhatsApp, Email, App Push — promotional, lifecycle, transactional in one calendar.',
    chip: 'multi-channel', to: '/crm' },
];

export default function Hub() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [me, setMe] = useState(null);
  const [billing, setBilling] = useState(null);
  const [recents, setRecents] = useState([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  // Bind the modal picker to the shared SelectionContext so opening the modal
  // pre-shows the user's current selection and confirming pushes the change
  // into Ad Copy / CRM / Marketing without an extra hop.
  const { selection: sharedSelection, setSelection: setSharedSelection } = useSelection();
  const [pickerSelection, setPickerSelection] = useState(sharedSelection);
  useEffect(() => { setPickerSelection(sharedSelection); }, [sharedSelection]);

  useEffect(() => {
    (async () => {
      try {
        const [meR, billR] = await Promise.all([
          api.get('/auth/me').catch(() => null),
          api.get('/auth/me/billing').catch(() => null),
        ]);
        if (meR) setMe(meR.data);
        if (billR) {
          setBilling(billR.data);
          // Last 5 unique offers — rough recents
          const seen = new Set();
          const rows = (billR.data.rows || []).filter((r) => {
            const k = (r.offer_name || '').toLowerCase();
            if (!k || seen.has(k)) return false;
            seen.add(k);
            return true;
          }).slice(0, 5);
          setRecents(rows);
        }
      } catch {}
    })();
  }, []);

  const greeting = (() => {
    const h = new Date().getHours();
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  })();

  const firstName = (user?.full_name || '').split(' ')[0] || '';

  // v2.6 — Identity strip: prefer the shared SelectionContext (what the user
  // actually picked, possibly across tools). Fall back to first assigned
  // hotel/brand, then "All workspaces" for admins / "No property assigned" otherwise.
  const identityName = (() => {
    const hotels = sharedSelection?._labels?.hotels || [];
    const brands = sharedSelection?._labels?.brands || [];
    const cities = sharedSelection?._labels?.cities || [];
    if (sharedSelection?.is_loyalty) return 'Club ITC';
    if (hotels.length === 1 && brands.length === 0 && cities.length === 0) return hotels[0].label;
    if (brands.length === 1 && hotels.length === 0 && cities.length === 0) return brands[0].label;
    const total = hotels.length + brands.length + cities.length;
    if (total > 1) {
      return `${total} entities · ${[
        hotels.length && `${hotels.length} hotel${hotels.length !== 1 ? 's' : ''}`,
        brands.length && `${brands.length} brand${brands.length !== 1 ? 's' : ''}`,
        cities.length && `${cities.length} cit${cities.length !== 1 ? 'ies' : 'y'}`,
      ].filter(Boolean).join(' · ')}`;
    }
    return (me?.scope_summary?.hotel_names?.[0])
      || (me?.scope_summary?.brand_names?.[0])
      || (user?.role === 'admin' ? 'All workspaces' : 'No property assigned');
  })();

  return (
    <div className="em-scope" style={{ padding: '8px 4px 32px' }}>
      {/* Hero */}
      <div className="em-hero">
        <div>
          <h1 className="em-display">
            {greeting}{firstName ? `, ${firstName}` : ''}. <em>Let's launch something.</em>
          </h1>
          <p className="sub">
            Your workspace is ready. Pick up a draft, clone last week's brief, or start fresh — every tool below begins <b>pre-filled</b>.
          </p>
        </div>
        <div className="em-hero-cta">
          <button className="em-btn" onClick={() => navigate('/crm')}>
            <MessageSquare size={14} /> Build a CRM campaign
          </button>
          <button className="em-btn primary" onClick={() => navigate('/adcopy')}>
            <Plus size={14} /> New Ad Copy
          </button>
        </div>
      </div>

      {/* Identity strip */}
      <div className="em-identity">
        <div className="em-ph" />
        <div>
          <div className="em-mono-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span>Active workspace</span>
            <span style={{ width: 4, height: 4, borderRadius: '50%', background: 'var(--em-accent)' }} />
            <span>identity captured once</span>
          </div>
          <h2 className="em-display">{identityName}</h2>
          <div className="em-chips">
            {me?.scope_summary?.brand_count > 0 && (
              <span className="em-pill accent">{me.scope_summary.brand_count} brand{me.scope_summary.brand_count !== 1 ? 's' : ''}</span>
            )}
            {me?.scope_summary?.hotel_count > 0 && (
              <span className="em-pill">{me.scope_summary.hotel_count} hotel{me.scope_summary.hotel_count !== 1 ? 's' : ''}</span>
            )}
            <span className="em-chip remember"><span className="dot" />Voice synced from training data</span>
            <span className="em-chip remember"><span className="dot" />{(billing?.rows?.length || 0)} past briefs</span>
          </div>
        </div>
        <div className="em-right">
          <button className="em-btn sm" onClick={() => setPickerOpen(true)}>Switch property / brand</button>
        </div>
      </div>

      {pickerOpen && (
        <div
          role="dialog"
          aria-modal="true"
          onClick={(e) => { if (e.target === e.currentTarget) setPickerOpen(false); }}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(22,21,19,0.45)',
            display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
            zIndex: 1000, paddingTop: '10vh',
          }}
        >
          <div className="em-card" style={{ width: 'min(640px, 92vw)', display: 'flex', flexDirection: 'column', gap: 14, overflow: 'visible' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <div>
                <div className="em-mono-label">Switch context</div>
                <h3 className="em-display" style={{ margin: '4px 0 0', fontSize: 22 }}>
                  Pick a <em>property, brand, city, or Club ITC</em>.
                </h3>
              </div>
              <button type="button" onClick={() => setPickerOpen(false)} className="em-btn sm ghost">
                <X size={14} />
              </button>
            </div>
            <p style={{ fontSize: 12.5, color: 'var(--em-ink-soft)', margin: 0 }}>
              Multi-select is on. Click rows to add/remove. The Ad Copy form will pre-fill from the chosen entities and ask whether you want a unified ad or one per entity.
            </p>
            {/* No overflow wrapper here — the picker dropdown is absolute-positioned
                and was being clipped by an outer overflow:auto. Picker dropdown
                already self-scrolls internally (max-height 320px). */}
            <IntelligentPropertyPicker
              value={pickerSelection}
              onChange={setPickerSelection}
              scopeSummary={me?.scope_summary || null}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, paddingTop: 8, borderTop: '1px solid var(--em-line)' }}>
              {(() => {
                const n = (pickerSelection?.hotel_ids?.length || 0)
                  + (pickerSelection?.brand_ids?.length || 0)
                  + (pickerSelection?.cities?.length || 0);
                return (
                  <div style={{ fontSize: 12.5, color: n > 0 ? 'var(--em-accent)' : 'var(--em-ink-soft)' }}>
                    {n === 0 ? 'Nothing selected yet' : `${n} ${n === 1 ? 'entity' : 'entities'} selected`}
                  </div>
                );
              })()}
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="em-btn" onClick={() => { setPickerSelection(null); }}>Clear</button>
                <button className="em-btn" onClick={() => setPickerOpen(false)}>Cancel</button>
                <button
                  className="em-btn primary"
                  onClick={() => {
                    setPickerOpen(false);
                    setSharedSelection(pickerSelection);
                    navigate('/adcopy', { state: { selection: pickerSelection } });
                  }}
                  disabled={
                    !pickerSelection ||
                    ((pickerSelection.hotel_ids?.length || 0) +
                      (pickerSelection.brand_ids?.length || 0) +
                      (pickerSelection.cities?.length || 0) === 0)
                  }
                >
                  Use this for Ad Copy
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Agents grid */}
      <div className="em-section-head">
        <div style={{ display: 'flex', alignItems: 'baseline' }}>
          <h3 className="em-display">Agents</h3>
          <span className="lead">Each agent inherits identity, brand voice, and guardrails. One feeds the next.</span>
        </div>
      </div>
      <div className="em-tools">
        {TOOLS.map((t) => {
          const Icon = t.icon;
          return (
            <div
              key={t.id}
              className={`em-tool ${t.featured ? 'featured' : ''}`}
              onClick={() => navigate(t.to)}
              role="button"
            >
              <div className="num">{t.num}</div>
              <div className="ic-lg"><Icon size={20} /></div>
              <h4>{t.title}</h4>
              <p>{t.blurb}</p>
              <div className="meta-row">
                <span className="em-chip">{t.chip}</span>
                <span className="arrow"><ArrowRight size={18} /></span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Recents + side */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: 24, marginTop: 24 }}>
        <div>
          <div className="em-section-head">
            <div style={{ display: 'flex', alignItems: 'baseline' }}>
              <h3 className="em-display">Pick up where you left off</h3>
              <span className="lead">{recents.length} recent</span>
            </div>
            <a href="/account" style={{ fontSize: 12.5, color: 'var(--em-ink-soft)', textDecoration: 'none' }}>View all →</a>
          </div>
          <div className="em-recents">
            {recents.length === 0 && (
              <div className="em-recent">
                <div className="glyph"><BookmarkCheck size={16} /></div>
                <div className="body">
                  <div className="t">No briefs yet</div>
                  <div className="s"><span>Generate your first ad to populate this list</span></div>
                </div>
              </div>
            )}
            {recents.map((r) => (
              <div key={r.id} className="em-recent" onClick={() => navigate('/adcopy')} role="button">
                <div className="glyph"><Megaphone size={16} /></div>
                <div className="body">
                  <div className="t">
                    {r.offer_name || 'Untitled brief'}
                    <span className="em-status">past</span>
                  </div>
                  <div className="s">
                    <span>{r.hotel_name}</span>
                    <span className="dot-sep" />
                    <span>{(r.platforms || []).slice(0, 3).join(' · ') || 'Ad copy'}</span>
                    <span className="dot-sep" />
                    <span>{(r.timestamp || '').slice(0, 10)}</span>
                  </div>
                </div>
                <div><ArrowRight size={16} /></div>
              </div>
            ))}
          </div>
        </div>

        <aside style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="em-panel">
            <h5>Property memory <span className="em-mono-label">↻ remembered</span></h5>
            <div style={{ display: 'grid', gap: 8 }}>
              {(() => {
                const isAdminish = user?.role === 'admin' || me?.scope_summary?.has_group;
                const brandVal = isAdminish ? 'All' : (me?.scope_summary?.brand_count ?? 0);
                const hotelVal = isAdminish ? 'All' : (me?.scope_summary?.hotel_count ?? 0);
                return (
                  <>
                    <Mem label="Brands" value={brandVal} />
                    <Mem label="Hotels" value={hotelVal} />
                    {me?.scope_summary?.city_count > 0 && (
                      <Mem label="Cities" value={me.scope_summary.city_count} />
                    )}
                    {me?.scope_summary?.has_loyalty && (
                      <Mem label="Loyalty" value="Club ITC" />
                    )}
                  </>
                );
              })()}
              <Mem label="Past briefs" value={billing?.rows?.length ?? 0} />
              <Mem label="Token visibility" value={me?.show_token_count ? 'visible' : 'hidden'} />
            </div>
          </div>

          <div className="em-panel">
            <h5>This week</h5>
            <div className="em-stat-row">
              <Stat v={(billing?.rows || []).filter((r) => isWithinDays(r.timestamp, 7)).length} l="Generations" />
              <Stat v={billing?.show_token_amount && billing?.total_cost_inr != null
                ? `₹${Number(billing.total_cost_inr).toFixed(2)}` : '—'} l="Spend (INR)" />
              <Stat v={recents.length} l="Recent briefs" />
              <Stat v={user?.role === 'admin' ? 'admin' : (user?.role || '').replace('_', ' ').slice(0, 12)} l="Role" />
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

function Mem({ label, value }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', borderRadius: 8, background: 'var(--em-surface-2)', border: '1px solid var(--em-line)', fontSize: 12.5 }}>
      <span style={{ color: 'var(--em-ink-soft)' }}>{label}</span>
      <span style={{ marginLeft: 'auto', fontWeight: 500, color: 'var(--em-ink)' }}>{value}</span>
    </div>
  );
}

function Stat({ v, l }) {
  return (
    <div className="em-stat">
      <div className="v">{v}</div>
      <div className="l">{l}</div>
    </div>
  );
}

function isWithinDays(iso, days) {
  if (!iso) return false;
  try {
    const t = new Date(iso).getTime();
    const cutoff = Date.now() - days * 24 * 3600 * 1000;
    return t >= cutoff;
  } catch { return false; }
}
