/**
 * Marketing Calendar — quarter grid view (v2.3).
 *
 * Read-only for now: aggregates the user's last 90 days of /auth/me/billing
 * rows by ISO week + channel, places them on the grid. Future v2.4: drag/drop
 * scheduling, "+ New campaign" modal that writes to a dedicated `campaigns`
 * Firestore collection.
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { useSelection } from '../contexts/SelectionContext';

const CHANNELS = [
  { id: 'google_search', label: 'Google Search', match: ['google_search'] },
  { id: 'meta_ads',      label: 'Meta Ads',      match: ['fb_single_image', 'fb_carousel', 'fb_video'] },
  { id: 'pmax',          label: 'Performance Max', match: ['pmax'] },
  { id: 'youtube',       label: 'YouTube',       match: ['youtube'] },
  { id: 'whatsapp',      label: 'WhatsApp',      match: ['whatsapp'] },
  { id: 'email',         label: 'Email',         match: ['email'] },
  { id: 'app_push',      label: 'App Push',      match: ['app_push'] },
];

function isoWeek(d) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil((((date - yearStart) / 86400000) + 1) / 7);
}

function quarterWeeks(quarterIdx, year) {
  // Q1 weeks 1-13, Q2 14-26, Q3 27-39, Q4 40-52(+53)
  const starts = [1, 14, 27, 40];
  const start = starts[quarterIdx];
  const end = quarterIdx === 3 ? 52 : starts[quarterIdx + 1] - 1;
  const out = [];
  for (let w = start; w <= end; w++) out.push({ year, week: w });
  return out;
}

function quarterFor(date) {
  const m = date.getMonth();
  return Math.floor(m / 3);
}

function quarterLabel(q, year) {
  const months = [['Jan', 'Mar'], ['Apr', 'Jun'], ['Jul', 'Sep'], ['Oct', 'Dec']][q];
  return `Q${q + 1} · ${months[0]} – ${months[1]} ${year}`;
}

function channelFor(platforms = []) {
  for (const ch of CHANNELS) {
    if (platforms.some((p) => ch.match.includes(p))) return ch.id;
  }
  return null;
}

export default function MarketingCalendar() {
  const navigate = useNavigate();
  const { selection } = useSelection();
  const [billing, setBilling] = useState(null);
  const [now] = useState(new Date());
  const [activeQ, setActiveQ] = useState(quarterFor(new Date()));
  // v2.5 — view-mode + group-value dropdowns.
  // Default sensibly based on the shared selection.
  const defaultGroupBy = (() => {
    if (selection?.is_loyalty) return 'loyalty';
    if ((selection?.brand_ids?.length || 0) > 0) return 'brand';
    if ((selection?.hotel_ids?.length || 0) > 0) return 'property';
    return 'property';
  })();
  const [groupBy, setGroupBy] = useState(defaultGroupBy);   // 'property' | 'campaign' | 'brand' | 'loyalty'
  const [groupValue, setGroupValue] = useState('');         // selected specific property / campaign / brand

  useEffect(() => {
    api.get('/auth/me/billing').then((r) => setBilling(r.data)).catch(() => setBilling({ rows: [] }));
  }, []);

  const year = now.getFullYear();
  const weeks = useMemo(() => quarterWeeks(activeQ, year), [activeQ, year]);

  // v2.5 — pre-filter audit rows by the active selection + group-value.
  const filteredRows = useMemo(() => {
    if (!billing?.rows) return [];
    let rows = billing.rows;
    // Honor shared selection first.
    if (selection?.is_loyalty || groupBy === 'loyalty') {
      rows = rows.filter((r) => (r.scope === 'loyalty') || (r.brand_id === 'club-itc'));
    } else {
      const hotelLabels = (selection?._labels?.hotels || []).map((h) => h.label);
      const brandIds = (selection?.brand_ids || []);
      if (hotelLabels.length || brandIds.length) {
        rows = rows.filter((r) =>
          (hotelLabels.length && hotelLabels.includes(r.hotel_name))
          || (brandIds.length && brandIds.includes(r.brand_id))
        );
      }
    }
    // Honor the group-value drill-down.
    if (groupValue) {
      if (groupBy === 'property') rows = rows.filter((r) => r.hotel_name === groupValue);
      else if (groupBy === 'campaign') rows = rows.filter((r) => r.offer_name === groupValue);
      else if (groupBy === 'brand') rows = rows.filter((r) => r.brand_id === groupValue);
    }
    return rows;
  }, [billing, selection, groupBy, groupValue]);

  // Distinct group values to populate the second dropdown.
  const groupValues = useMemo(() => {
    if (!billing?.rows) return [];
    const set = new Set();
    for (const r of billing.rows) {
      if (groupBy === 'property' && r.hotel_name) set.add(r.hotel_name);
      else if (groupBy === 'campaign' && r.offer_name) set.add(r.offer_name);
      else if (groupBy === 'brand' && r.brand_id) set.add(r.brand_id);
    }
    return [...set].sort();
  }, [billing, groupBy]);

  const events = useMemo(() => {
    const map = {};
    for (const ch of CHANNELS) map[ch.id] = {};
    for (const r of filteredRows) {
      const ts = new Date(r.timestamp || '');
      if (Number.isNaN(ts.getTime())) continue;
      const ch = channelFor(r.platforms);
      if (!ch) continue;
      const w = isoWeek(ts);
      if (!weeks.find((x) => x.week === w)) continue;
      if (!map[ch][w]) map[ch][w] = [];
      map[ch][w].push(r);
    }
    return map;
  }, [filteredRows, weeks]);

  const hasAnyEvents = Object.values(events).some((wkmap) => Object.keys(wkmap).length > 0);

  return (
    <div className="em-scope" style={{ padding: '8px 4px 32px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 18, gap: 12, flexWrap: 'wrap' }}>
        <div>
          <div className="em-mono-label" style={{ marginBottom: 4 }}>Home / Marketing Calendar</div>
          <h1 className="em-display" style={{ fontSize: 36, margin: 0 }}>
            Create <em>Marketing Calendar</em>
          </h1>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="em-btn" onClick={() => navigate('/adcopy')}>Import last brief</button>
          <button className="em-btn primary" onClick={() => navigate('/adcopy')}>+ New campaign</button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 18, padding: '14px 18px', background: 'var(--em-surface)', border: '1px solid var(--em-line)', borderRadius: 10 }}>
        <div className="em-mode-toggle">
          {[0, 1, 2, 3].map((q) => (
            <button key={q} aria-selected={activeQ === q} onClick={() => setActiveQ(q)}>
              Q{q + 1}
            </button>
          ))}
        </div>
        <span style={{ color: 'var(--em-ink-faint)', fontSize: 12 }}>·</span>
        <span className="em-chip">{quarterLabel(activeQ, year)}</span>

        {/* v2.5 — view-mode dropdown */}
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--em-ink-soft)' }}>
          View by
          <select
            value={groupBy}
            onChange={(e) => { setGroupBy(e.target.value); setGroupValue(''); }}
            style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid var(--em-line)', background: 'var(--em-surface)', fontSize: 12 }}
          >
            <option value="property">Property</option>
            <option value="campaign">Campaign</option>
            <option value="brand">Brand</option>
            <option value="loyalty">Club ITC (Loyalty)</option>
          </select>
        </label>

        {/* v2.5 — drill-down to a specific value */}
        {groupBy !== 'loyalty' && groupValues.length > 0 && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--em-ink-soft)' }}>
            Pick {groupBy}
            <select
              value={groupValue}
              onChange={(e) => setGroupValue(e.target.value)}
              style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid var(--em-line)', background: 'var(--em-surface)', fontSize: 12, maxWidth: 220 }}
            >
              <option value="">All ({groupValues.length})</option>
              {groupValues.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </label>
        )}

        {(selection?._labels?.hotels?.length || selection?._labels?.brands?.length || selection?.is_loyalty) ? (
          <span className="em-pill accent" style={{ fontSize: 11 }}>
            scope: {selection?.is_loyalty ? 'Club ITC'
              : (selection?._labels?.brands?.[0]?.label || selection?._labels?.hotels?.map((h) => h.label).join(', ').slice(0, 40))}
          </span>
        ) : (
          <span className="em-chip muted">All scope</span>
        )}
      </div>

      <div className="em-cal-shell">
        <div className="em-cal-row head">
          <div className="cell" style={{ borderLeft: 'none', textAlign: 'left', paddingLeft: 12 }}>Channel</div>
          {weeks.map((w) => (
            <div key={w.week} className="cell">W{w.week}</div>
          ))}
        </div>

        {CHANNELS.map((ch) => (
          <div key={ch.id} className="em-cal-row">
            <div className="channel">{ch.label}</div>
            {weeks.map((w, i) => {
              const slotEvents = events[ch.id]?.[w.week] || [];
              if (slotEvents.length === 0) {
                return <div key={w.week} className="cell" style={{ minHeight: 64 }} />;
              }
              const e = slotEvents[0];
              const accent = i % 2 === 0;
              return (
                <div
                  key={w.week}
                  className={`em-cal-event ${accent ? 'accent' : ''}`}
                  title={`${e.offer_name || ''} · ${e.hotel_name || ''}`}
                  onClick={() => navigate('/account')}
                  role="button"
                >
                  {(e.offer_name || 'Brief').slice(0, 22)}
                  {slotEvents.length > 1 && <small> +{slotEvents.length - 1}</small>}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {!hasAnyEvents && (
        <div className="em-panel" style={{ marginTop: 16 }}>
          <h5>Nothing on the calendar yet</h5>
          <p style={{ color: 'var(--em-ink-soft)', fontSize: 13 }}>
            Generate a few ads or CRM campaigns and they'll appear here grouped by week and channel.
            Drag-and-drop scheduling and "+ New campaign" are coming in v2.4.
          </p>
        </div>
      )}
    </div>
  );
}
