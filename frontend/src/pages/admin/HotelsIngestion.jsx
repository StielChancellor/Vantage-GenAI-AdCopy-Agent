/**
 * HotelsIngestion — admin-only page for bulk-importing hotels (v2.2).
 *
 * Two paths:
 *   1. CSV/XLSX upload → POST /hotels/ingest. Auto-creates brands and tags hotels.
 *   2. Manual single-hotel form → POST /hotels.
 *
 * Required CSV columns: hotel_name, hotel_code, brand_name
 * Optional CSV columns: rooms_count, fnb_count, website_url, gmb_url
 *
 * Hotel_code + brand_name are organizational metadata only — they are NEVER
 * sent to the model. Rooms_count + fnb_count ARE injected into prompts.
 */
import { useState } from 'react';
import toast from 'react-hot-toast';
import api from '../../services/api';

const TEMPLATE_HEADER = 'hotel_name,hotel_code,brand_name,city,rooms_count,fnb_count,website_url,gmb_url\n';

export default function HotelsIngestion() {
  const [mode, setMode] = useState('csv');           // 'csv' | 'manual'
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [report, setReport] = useState(null);

  // Manual form
  const [hotel, setHotel] = useState({
    hotel_name: '', hotel_code: '', brand_name: '', city: '',
    rooms_count: '', fnb_count: '', website_url: '', gmb_url: '',
  });

  const submitCsv = async () => {
    if (!file) {
      toast.error('Pick a file first.');
      return;
    }
    setUploading(true);
    setReport(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const r = await api.post('/hotels/ingest', form, { headers: { 'Content-Type': 'multipart/form-data' } });
      setReport(r.data);
      const summary = `${r.data.created_brands} brand${r.data.created_brands !== 1 ? 's' : ''} · ${r.data.created_hotels} hotel${r.data.created_hotels !== 1 ? 's' : ''} created, ${r.data.updated_hotels} updated`;
      toast.success(`Ingested: ${summary}`, { duration: 6000 });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Ingest failed');
    } finally {
      setUploading(false);
    }
  };

  const submitManual = async () => {
    if (!hotel.hotel_name || !hotel.hotel_code || !hotel.brand_name) {
      toast.error('Hotel name, hotel code, and brand name are required.');
      return;
    }
    setUploading(true);
    try {
      const form = new FormData();
      Object.entries(hotel).forEach(([k, v]) => {
        if (v !== '' && v != null) form.append(k, v);
      });
      const r = await api.post('/hotels', form, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success(`Hotel ${r.data.action}: ${hotel.hotel_name}`);
      setHotel({ hotel_name: '', hotel_code: '', brand_name: '', city: '', rooms_count: '', fnb_count: '', website_url: '', gmb_url: '' });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Save failed');
    } finally {
      setUploading(false);
    }
  };

  const downloadTemplate = () => {
    const blob = new Blob([TEMPLATE_HEADER], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'vantage-hotels-template.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="em-card" style={{ display: 'grid', gap: 18 }}>
      <div>
        <h3 className="em-display" style={{ margin: 0, fontSize: 26 }}>
          Hotels <em>Ingestion</em>
        </h3>
        <p style={{ color: 'var(--em-ink-soft)', fontSize: 13, margin: '4px 0 0' }}>
          Bulk-create hotels from a CSV. Brand hierarchy is built automatically from the brand_name column.
          Rooms count, F&B count and city are used by the model when writing copy. Hotel code + brand name are organizational only.
          {' '}<strong>v2.4 — `city` is now an optional column</strong> that also drives city-level user grants.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <button type="button" className="em-mode-card" aria-selected={mode === 'csv'} onClick={() => setMode('csv')}>
          <div className="t">CSV / Excel upload</div>
          <div className="s">Bulk · multiple hotels at once</div>
        </button>
        <button type="button" className="em-mode-card" aria-selected={mode === 'manual'} onClick={() => setMode('manual')}>
          <div className="t">Add a single hotel</div>
          <div className="s">Manual form</div>
        </button>
        <button type="button" className="em-mode-card" onClick={downloadTemplate}>
          <div className="t">Download CSV template</div>
          <div className="s">3 required + 5 optional columns</div>
        </button>
      </div>

      {mode === 'csv' && (
        <>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="file" accept=".csv,.xlsx,.xls" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            <button type="button" disabled={uploading || !file} onClick={submitCsv} className="btn-primary">
              {uploading ? 'Ingesting…' : 'Ingest hotels'}
            </button>
          </div>
          {report && (
            <div style={{ background: 'var(--em-surface-2)', border: '1px solid var(--em-line)', borderRadius: 10, padding: 14, fontSize: 13 }}>
              <div className="em-mono-label" style={{ marginBottom: 8 }}>Result</div>
              <div>
                <strong>{report.created_brands}</strong> brands created ·{' '}
                <strong>{report.created_hotels}</strong> hotels created ·{' '}
                <strong>{report.updated_hotels}</strong> updated ·{' '}
                <strong>{report.skipped}</strong> skipped
              </div>
              {report.errors?.length > 0 && (
                <details style={{ marginTop: 8 }}>
                  <summary style={{ cursor: 'pointer' }}>{report.errors.length} row error{report.errors.length !== 1 ? 's' : ''}</summary>
                  <ul style={{ margin: '6px 0 0 16px', padding: 0, fontSize: 12, color: 'var(--em-ink-soft)' }}>
                    {report.errors.slice(0, 10).map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
                </details>
              )}
              {report.brand_tree?.length > 0 && (
                <details style={{ marginTop: 8 }}>
                  <summary style={{ cursor: 'pointer' }}>Brand tree</summary>
                  <div style={{ marginTop: 8 }}>
                    {report.brand_tree.map((b) => (
                      <div key={b.brand_name} className="em-tree-node brand" style={{ marginBottom: 6 }}>
                        <div className="em-tree-title">{b.brand_name}</div>
                        <div className="em-tree-meta">{b.hotels.length} hotel{b.hotels.length !== 1 ? 's' : ''}</div>
                        <ul style={{ margin: '6px 0 0 16px', padding: 0 }}>
                          {b.hotels.map((h) => (
                            <li key={h.hotel_code} style={{ fontSize: 12 }}>{h.hotel_name} <span style={{ color: 'var(--em-ink-faint)' }}>· {h.hotel_code}</span></li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          )}
        </>
      )}

      {mode === 'manual' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {[
            ['hotel_name', 'Hotel name *'],
            ['hotel_code', 'Hotel code *'],
            ['brand_name', 'Brand name *'],
            ['city', 'City'],
            ['rooms_count', 'Rooms count'],
            ['fnb_count', 'F&B outlet count'],
            ['website_url', 'Website URL'],
            ['gmb_url', 'Google Maps URL'],
          ].map(([k, label]) => (
            <label key={k}>
              <div className="em-mono-label">{label}</div>
              <input
                value={hotel[k]}
                onChange={(e) => setHotel({ ...hotel, [k]: e.target.value })}
                type={k.endsWith('_count') ? 'number' : 'text'}
              />
            </label>
          ))}
          <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end' }}>
            <button type="button" disabled={uploading} onClick={submitManual} className="btn-primary">
              {uploading ? 'Saving…' : 'Save hotel'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
