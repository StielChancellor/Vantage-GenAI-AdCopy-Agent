/**
 * RecentGenerations — "Pick up where you left off" panel below the Ad Copy form (v2.4).
 *
 * Calls /generate/recent (filtered by hotel_id/brand_id when a selection is active).
 * Each row shows when, hotel/brand, offer, platforms, and a "Re-use brief" button
 * that repopulates the form fields from that audit row via onReuse(brief).
 */
import { useEffect, useState } from 'react';
import { Megaphone, RefreshCw, Clock } from 'lucide-react';
import { getRecentGenerations } from '../services/api';

const PLATFORM_LABELS = {
  google_search: 'Google Search',
  fb_single_image: 'FB Image',
  fb_carousel: 'FB Carousel',
  fb_video: 'FB Video',
  performance_max: 'PMax',
  youtube: 'YouTube',
};

export default function RecentGenerations({ hotelId = '', brandId = '', limit = 10, onReuse }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await getRecentGenerations({ limit, hotelId, brandId });
      setRows(r.data?.generations || []);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hotelId, brandId]);

  if (!loading && rows.length === 0) {
    return (
      <div className="em-card" style={{ marginTop: 18 }}>
        <div className="em-mono-label">Pick up where you left off</div>
        <p style={{ fontSize: 13, color: 'var(--em-ink-soft)', marginTop: 6 }}>
          No recent generations{hotelId || brandId ? ' for this selection' : ''} yet.
        </p>
      </div>
    );
  }

  return (
    <div className="em-card" style={{ marginTop: 18 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <div className="em-mono-label">Pick up where you left off</div>
        <button type="button" className="em-btn" onClick={load} disabled={loading} title="Refresh">
          <RefreshCw size={12} /> {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>
      <div style={{ display: 'grid', gap: 8 }}>
        {rows.map((r) => (
          <div key={r.id} className="em-recent-row" style={{
            display: 'grid',
            gridTemplateColumns: '20px 1fr auto',
            alignItems: 'center',
            gap: 12,
            padding: '10px 12px',
            border: '1px solid var(--em-line)',
            borderRadius: 8,
            background: 'var(--em-surface)',
          }}>
            <Megaphone size={14} style={{ color: 'var(--em-ink-faint)' }} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 14, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {r.offer_name || 'Untitled offer'}
              </div>
              <div style={{ fontSize: 12, color: 'var(--em-ink-soft)', marginTop: 2 }}>
                <Clock size={10} style={{ verticalAlign: '-1px', marginRight: 4 }} />
                {(r.timestamp || '').slice(0, 10)} · {r.hotel_name || 'Brand-level'}
                {' · '}
                {(r.platforms || []).map((p) => PLATFORM_LABELS[p] || p).join(', ')}
              </div>
            </div>
            <button
              type="button"
              className="em-btn accent"
              onClick={() => onReuse?.(r)}
              title="Repopulate the form with this brief"
            >
              Re-use brief
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
