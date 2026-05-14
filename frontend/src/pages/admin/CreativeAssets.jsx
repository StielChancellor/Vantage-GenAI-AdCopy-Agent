/**
 * Admin → Creative Assets (v2.7).
 *
 * Bulk-upload campaign packs (zip = images + ad_copies.xlsx) used as the
 * training corpus for `/ideation`. Each image is captioned by Gemini Vision,
 * the caption + headline + body is embedded, and a `creative_assets/{id}`
 * Firestore doc is written. Progress polls `ingestion_progress/{run_id}`.
 */
import { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { Upload, Loader2, Image as ImageIcon, RefreshCcw } from 'lucide-react';
import IntelligentPropertyPicker from '../../components/IntelligentPropertyPicker';
import {
  uploadCreativePack,
  listCreativeAssets,
  getTrainingProgress,
} from '../../services/api';

function makeRunId() {
  return `pack-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function CreativeAssets() {
  const [pickerSel, setPickerSel] = useState(null);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(null);
  const [runId, setRunId] = useState('');
  const [assets, setAssets] = useState([]);
  const [loadingAssets, setLoadingAssets] = useState(false);
  const fileInputRef = useRef(null);
  const pollRef = useRef(null);

  const brandId = (pickerSel?.brand_ids || [])[0] || pickerSel?.brand_id || '';
  const brandLabel = (pickerSel?._labels?.brands || [])[0]?.label || '';

  const refreshAssets = async () => {
    setLoadingAssets(true);
    try {
      const r = await listCreativeAssets({ brandId, limit: 60 });
      setAssets(r.data?.assets || []);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not load assets.');
    } finally {
      setLoadingAssets(false);
    }
  };

  useEffect(() => {
    refreshAssets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brandId]);

  // Poll progress while a run is in-flight.
  useEffect(() => {
    if (!runId) return undefined;
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await getTrainingProgress(runId);
        if (cancelled) return;
        setProgress(r.data || null);
        if (r.data?.status === 'completed' || r.data?.status === 'failed') {
          refreshAssets();
          return;
        }
      } catch {/* tolerate transient */}
      pollRef.current = setTimeout(tick, 1200);
    };
    pollRef.current = setTimeout(tick, 600);
    return () => {
      cancelled = true;
      if (pollRef.current) clearTimeout(pollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  const onUpload = async () => {
    if (!file) {
      toast.error('Choose a .zip first.');
      return;
    }
    if (!brandId) {
      toast.error('Pick a brand first — assets are scoped per brand.');
      return;
    }
    setUploading(true);
    const rid = makeRunId();
    setRunId(rid);
    setProgress({ phase: 'starting', percent: 0, status: 'pending', message: 'Uploading…' });
    try {
      await uploadCreativePack(file, brandId, rid);
      toast.success('Pack uploaded; captioning in progress.');
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed.');
      setProgress({ status: 'failed', message: 'Upload failed.', percent: 0 });
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="page-shell">
      <header className="page-header">
        <div className="page-title-row">
          <ImageIcon size={20} />
          <h1>Creative Assets</h1>
        </div>
        <p className="page-subtitle">
          Upload past campaign packs (zip with images + ad_copies.xlsx). Each image is
          captioned by Gemini Vision and indexed for Campaign Ideation.
        </p>
      </header>

      <section className="em-card" style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <h2 style={{ margin: 0 }}>Upload a campaign pack</h2>

        <div className="form-group">
          <label>Brand *</label>
          <IntelligentPropertyPicker
            value={pickerSel}
            onChange={setPickerSel}
            scopeSummary={null}
            placeholder="Pick the brand this pack belongs to…"
          />
          <p style={{ fontSize: 12, color: 'var(--em-ink-soft)', marginTop: 4 }}>
            One brand per pack. Mixed-brand zips: upload separately.
          </p>
        </div>

        <div className="form-group">
          <label>Zip file *</label>
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          <p style={{ fontSize: 12, color: 'var(--em-ink-soft)', marginTop: 4 }}>
            Required: <code>ad_copies.xlsx</code> with columns <code>image_filename, headline, body</code>.
            Optional: <code>cta, platform, persona, hero_offer, campaign_name, season, theme</code>.
          </p>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button className="btn btn-primary" onClick={onUpload} disabled={uploading || !file || !brandId}>
            {uploading ? <Loader2 size={16} className="spin" /> : <Upload size={16} />}
            Upload &amp; caption
          </button>
        </div>

        {progress && (
          <div className="em-card" style={{ padding: 12, marginTop: 4 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--em-ink-soft)' }}>
              <span>{progress.phase} · {progress.status}</span>
              <span>{progress.percent || 0}%</span>
            </div>
            <div style={{ marginTop: 6, height: 6, background: 'var(--em-bg-soft, #efeae1)', borderRadius: 3, overflow: 'hidden' }}>
              <div
                style={{
                  width: `${Math.min(100, progress.percent || 0)}%`,
                  height: '100%',
                  background: 'var(--primary, #a93226)',
                  transition: 'width 0.3s',
                }}
              />
            </div>
            <p style={{ marginTop: 6, fontSize: 13 }}>{progress.message}</p>
          </div>
        )}
      </section>

      <section style={{ marginTop: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
          <h2 style={{ margin: 0 }}>Ingested assets</h2>
          <span style={{ color: 'var(--em-ink-soft)' }}>
            {brandLabel ? `Brand: ${brandLabel}` : 'All brands'} · {assets.length} item{assets.length === 1 ? '' : 's'}
          </span>
          <button className="btn btn-outline btn-sm" onClick={refreshAssets} disabled={loadingAssets}>
            {loadingAssets ? <Loader2 size={14} className="spin" /> : <RefreshCcw size={14} />}
            Refresh
          </button>
        </div>

        {assets.length === 0 ? (
          <div className="em-card" style={{ padding: 18, color: 'var(--em-ink-soft)' }}>
            No assets ingested yet for this brand.
          </div>
        ) : (
          <div className="shortlist-grid">
            {assets.map((a) => {
              const cap = a.caption_json || {};
              const motifs = Array.isArray(cap.motifs) ? cap.motifs.join(', ') : '';
              const palette = Array.isArray(cap.palette_tokens) ? cap.palette_tokens.join(', ') : '';
              return (
                <article key={a.id} className="em-card shortlist-card">
                  {a.signed_url ? (
                    <img
                      src={a.signed_url}
                      alt={a.image_filename}
                      style={{ width: '100%', borderRadius: 4, aspectRatio: '4/3', objectFit: 'cover' }}
                    />
                  ) : (
                    <div style={{ aspectRatio: '4/3', background: 'var(--em-bg-soft, #efeae1)', display: 'grid', placeItems: 'center', color: 'var(--em-ink-soft)' }}>
                      No preview
                    </div>
                  )}
                  <div className="shortlist-card-head">
                    <h3 style={{ fontSize: 14, margin: 0 }}>{a.campaign_name || a.image_filename}</h3>
                  </div>
                  {a.headline && (
                    <p className="shortlist-tagline" style={{ fontStyle: 'normal' }}>"{a.headline}"</p>
                  )}
                  <div className="shortlist-section">
                    <span className="em-mono-label">Caption</span>
                    <p>
                      mood: {cap.mood || '—'} · hero: {cap.hero_subject || '—'}<br />
                      palette: {palette || '—'} · motifs: {motifs || '—'}<br />
                      logo: {cap.logo_unit_placement || '—'}
                    </p>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
