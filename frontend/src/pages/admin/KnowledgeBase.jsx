/**
 * KnowledgeBase — admin-only hierarchical view (v2.2).
 *
 * Reads /api/v1/kb/tree and renders brand → [USPs, training notes] → hotels[USPs, training notes].
 * Editing is intentionally not supported here — clicking the "Update" button on
 * a row redirects to the relevant Training upload pre-filled with the entity context.
 */
import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import api from '../../services/api';

export default function KnowledgeBase() {
  const [tree, setTree] = useState(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState({});   // { [brand_id]: true, [`hotel:${hotel_id}`]: true }

  useEffect(() => {
    (async () => {
      try {
        const r = await api.get('/kb/tree');
        setTree(r.data);
      } catch (err) {
        toast.error(err.response?.data?.detail || 'Failed to load knowledge base');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const toggle = (key) => setOpen({ ...open, [key]: !open[key] });

  if (loading) return <div className="em-card">Loading knowledge base…</div>;
  if (!tree?.brands?.length) {
    return (
      <div className="em-card">
        <h3 className="em-display" style={{ margin: 0 }}>Knowledge Base</h3>
        <p style={{ color: 'var(--em-ink-soft)', marginTop: 8 }}>
          No brands yet. Use <strong>Hotels Ingestion</strong> to create brands and hotels, then run a <strong>Brand & USP</strong> training to populate this view.
        </p>
      </div>
    );
  }

  return (
    <div className="em-card em-tree" style={{ display: 'grid', gap: 12 }}>
      <div>
        <h3 className="em-display" style={{ margin: 0, fontSize: 26 }}>
          Knowledge <em>Base</em>
        </h3>
        <p style={{ color: 'var(--em-ink-soft)', fontSize: 13, margin: '4px 0 0' }}>
          The brands, USPs, and training notes the system has learned. Visible to admins only.
          Edits flow through the Training module — click <em>Update</em> on a row to add more data.
        </p>
      </div>

      {tree.brands.map((b) => {
        const bOpen = !!open[b.brand_id];
        return (
          <div key={b.brand_id} className="em-tree-node brand">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }} onClick={() => toggle(b.brand_id)}>
              <div>
                <div className="em-tree-title">{b.brand_name}</div>
                <div className="em-tree-meta">
                  {b.hotel_count} hotel{b.hotel_count !== 1 ? 's' : ''} · {b.usps?.length || 0} brand USP{(b.usps?.length || 0) !== 1 ? 's' : ''} · {b.training_notes?.length || 0} note{(b.training_notes?.length || 0) !== 1 ? 's' : ''}
                </div>
              </div>
              <span className="em-mono-label">{bOpen ? '−' : '+'}</span>
            </div>

            {bOpen && (
              <div className="em-tree-children" style={{ marginTop: 12 }}>
                {b.usps?.length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <div className="em-mono-label">Brand USPs</div>
                    <ul style={{ margin: '4px 0 0 16px' }}>
                      {b.usps.map((u, i) => <li key={i} style={{ fontSize: 13 }}>{u.usp}</li>)}
                    </ul>
                  </div>
                )}
                {b.training_notes?.length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <div className="em-mono-label">Training notes</div>
                    <ul style={{ margin: '4px 0 0 16px', listStyle: 'none', padding: 0 }}>
                      {b.training_notes.slice(0, 5).map((n, i) => (
                        <li key={i} style={{ fontSize: 12.5, color: 'var(--em-ink-soft)', borderLeft: '2px solid var(--em-line)', paddingLeft: 8, marginBottom: 4 }}>
                          {n.remark}
                          <div className="em-mono-label" style={{ marginTop: 2 }}>{(n.section_type || '').replace('_', ' ')} · {(n.created_at || '').slice(0, 10)}</div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {b.hotels?.length > 0 && (
                  <div style={{ marginTop: 8 }}>
                    <div className="em-mono-label" style={{ marginBottom: 6 }}>Hotels under {b.brand_name}</div>
                    {b.hotels.map((h) => {
                      const hKey = `hotel:${h.hotel_id}`;
                      const hOpen = !!open[hKey];
                      return (
                        <div key={h.hotel_id} className="em-tree-node" style={{ marginBottom: 6 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }} onClick={() => toggle(hKey)}>
                            <div>
                              <div className="em-tree-title">{h.hotel_name}</div>
                              <div className="em-tree-meta">
                                {h.hotel_code && <>code {h.hotel_code} · </>}
                                {h.rooms_count ? `${h.rooms_count} rooms · ` : ''}
                                {h.fnb_count ? `${h.fnb_count} F&B · ` : ''}
                                {h.usps?.length || 0} USP{(h.usps?.length || 0) !== 1 ? 's' : ''} · {h.training_notes?.length || 0} note{(h.training_notes?.length || 0) !== 1 ? 's' : ''}
                              </div>
                            </div>
                            <span className="em-mono-label">{hOpen ? '−' : '+'}</span>
                          </div>
                          {hOpen && (
                            <div style={{ marginTop: 10 }}>
                              {h.usps?.length > 0 && (
                                <>
                                  <div className="em-mono-label">USPs</div>
                                  <ul style={{ margin: '4px 0 8px 16px' }}>
                                    {h.usps.map((u, i) => <li key={i} style={{ fontSize: 13 }}>{u.usp}</li>)}
                                  </ul>
                                </>
                              )}
                              {h.training_notes?.length > 0 && (
                                <>
                                  <div className="em-mono-label">Training notes</div>
                                  <ul style={{ margin: '4px 0 0 16px', listStyle: 'none', padding: 0 }}>
                                    {h.training_notes.slice(0, 5).map((n, i) => (
                                      <li key={i} style={{ fontSize: 12.5, color: 'var(--em-ink-soft)', borderLeft: '2px solid var(--em-line)', paddingLeft: 8, marginBottom: 4 }}>
                                        {n.remark}
                                        <div className="em-mono-label" style={{ marginTop: 2 }}>{(n.section_type || '').replace('_', ' ')} · {(n.created_at || '').slice(0, 10)}</div>
                                      </li>
                                    ))}
                                  </ul>
                                </>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
