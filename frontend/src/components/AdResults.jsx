import { useState } from 'react';
import { Copy, Download, CheckCircle, Clock, Coins } from 'lucide-react';
import toast from 'react-hot-toast';

export default function AdResults({ data }) {
  const [copiedId, setCopiedId] = useState(null);

  const copyToClipboard = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    toast.success('Copied!');
    setTimeout(() => setCopiedId(null), 2000);
  };

  const downloadCSV = () => {
    const rows = [['Platform', 'Type', 'Index', 'Text']];
    data.variants.forEach((v) => {
      v.headlines.forEach((h, i) => rows.push([v.platform, 'Headline', i + 1, h]));
      v.descriptions.forEach((d, i) => rows.push([v.platform, 'Description', i + 1, d]));
      if (v.captions) {
        v.captions.forEach((c, i) => rows.push([v.platform, 'Caption', i + 1, c]));
      }
    });

    const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `adcopy_${data.hotel_name.replace(/\s+/g, '_')}_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('CSV downloaded!');
  };

  return (
    <div className="ad-results">
      <div className="results-header">
        <h2>Generated Ad Copy</h2>
        <div className="results-meta">
          <span className="stat-badge tokens">
            <Coins size={13} /> {data.tokens_used?.toLocaleString()} tokens
          </span>
          {data.time_seconds != null && (
            <span className="stat-badge time">
              <Clock size={13} /> {data.time_seconds.toFixed(1)}s
            </span>
          )}
          <button className="btn btn-sm btn-outline" onClick={downloadCSV}>
            <Download size={14} /> CSV
          </button>
        </div>
      </div>

      {data.variants.map((variant, vi) => (
        <div key={vi} className="platform-section">
          <h3 className="platform-title">{variant.platform.replace(/_/g, ' ').toUpperCase()}</h3>

          <div className="ad-group">
            <h4>Headlines</h4>
            {variant.headlines.map((h, i) => {
              const id = `h-${vi}-${i}`;
              return (
                <div key={id} className="ad-item">
                  <span className="ad-index">{i + 1}</span>
                  <span className="ad-text">{h}</span>
                  <span className="char-count">{h.length} chars</span>
                  <button className="btn-icon" onClick={() => copyToClipboard(h, id)}>
                    {copiedId === id ? <CheckCircle size={14} /> : <Copy size={14} />}
                  </button>
                </div>
              );
            })}
          </div>

          <div className="ad-group">
            <h4>Descriptions</h4>
            {variant.descriptions.map((d, i) => {
              const id = `d-${vi}-${i}`;
              return (
                <div key={id} className="ad-item">
                  <span className="ad-index">{i + 1}</span>
                  <span className="ad-text">{d}</span>
                  <span className="char-count">{d.length} chars</span>
                  <button className="btn-icon" onClick={() => copyToClipboard(d, id)}>
                    {copiedId === id ? <CheckCircle size={14} /> : <Copy size={14} />}
                  </button>
                </div>
              );
            })}
          </div>

          {variant.captions && variant.captions.length > 0 && (
            <div className="ad-group">
              <h4>Captions</h4>
              {variant.captions.map((c, i) => {
                const id = `c-${vi}-${i}`;
                return (
                  <div key={id} className="ad-item">
                    <span className="ad-index">{i + 1}</span>
                    <span className="ad-text">{c}</span>
                    <span className="char-count">{c.length} chars</span>
                    <button className="btn-icon" onClick={() => copyToClipboard(c, id)}>
                      {copiedId === id ? <CheckCircle size={14} /> : <Copy size={14} />}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
