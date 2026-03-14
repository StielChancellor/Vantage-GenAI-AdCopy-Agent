import { useState } from 'react';
import { Copy, Download, CheckCircle, Clock, Coins, MessageSquare, Send } from 'lucide-react';
import toast from 'react-hot-toast';

export default function AdResults({ data, form, onRefine, refining }) {
  const [copiedId, setCopiedId] = useState(null);
  const [feedback, setFeedback] = useState('');

  const copyToClipboard = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    toast.success('Copied!');
    setTimeout(() => setCopiedId(null), 2000);
  };

  const downloadCSV = () => {
    const rows = [['Platform', 'Type', 'Index', 'Text']];
    data.variants.forEach((v) => {
      if (v.captions && v.platform === 'fb_carousel') {
        v.captions.forEach((c, i) => rows.push([v.platform, 'Primary Text', i + 1, c]));
      }
      v.headlines.forEach((h, i) => rows.push([v.platform, 'Headline', i + 1, h]));
      v.descriptions.forEach((d, i) => rows.push([v.platform, 'Description', i + 1, d]));
      if (v.captions && v.platform !== 'fb_carousel') {
        v.captions.forEach((c, i) => rows.push([v.platform, 'Caption', i + 1, c]));
      }
      if (v.card_suggestions) {
        v.card_suggestions.forEach((s, i) => rows.push([v.platform, 'Card Suggestion', i + 1, s]));
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

  const handleFeedbackSubmit = (e) => {
    e.preventDefault();
    if (!feedback.trim()) {
      toast.error('Please enter feedback');
      return;
    }
    onRefine(feedback.trim());
    setFeedback('');
  };

  const renderAdItem = (text, id, label) => (
    <div key={id} className="ad-item">
      <span className="ad-index">{label}</span>
      <span className="ad-text">{text}</span>
      <span className="char-count">{text.length} chars</span>
      <button className="btn-icon" onClick={() => copyToClipboard(text, id)}>
        {copiedId === id ? <CheckCircle size={14} /> : <Copy size={14} />}
      </button>
    </div>
  );

  const renderCarouselVariant = (variant, vi) => (
    <div key={vi} className="platform-section">
      <h3 className="platform-title">{variant.platform.replace(/_/g, ' ').toUpperCase()}</h3>

      {/* Primary Text (captions) shown first for fb_carousel */}
      {variant.captions && variant.captions.length > 0 && (
        <div className="ad-group">
          <h4>Primary Text</h4>
          {variant.captions.map((c, i) => renderAdItem(c, `c-${vi}-${i}`, i + 1))}
        </div>
      )}

      {/* Carousel Cards - grouped with headline + description + visual suggestion per card */}
      <div className="ad-group">
        <h4>Carousel Cards</h4>
        {variant.headlines.map((h, i) => (
          <div key={`card-${vi}-${i}`} className="carousel-card-group">
            <div className="card-label">Card {i + 1}</div>
            {variant.card_suggestions && variant.card_suggestions[i] && (
              <div className="ad-item card-suggestion">
                <span className="ad-index">🖼</span>
                <span className="ad-text">{variant.card_suggestions[i]}</span>
                <button className="btn-icon" onClick={() => copyToClipboard(variant.card_suggestions[i], `cs-${vi}-${i}`)}>
                  {copiedId === `cs-${vi}-${i}` ? <CheckCircle size={14} /> : <Copy size={14} />}
                </button>
              </div>
            )}
            {renderAdItem(h, `ch-${vi}-${i}`, 'H')}
            {variant.descriptions[i] && renderAdItem(variant.descriptions[i], `cd-${vi}-${i}`, 'D')}
          </div>
        ))}
      </div>
    </div>
  );

  const renderStandardVariant = (variant, vi) => (
    <div key={vi} className="platform-section">
      <h3 className="platform-title">{variant.platform.replace(/_/g, ' ').toUpperCase()}</h3>

      <div className="ad-group">
        <h4>Headlines</h4>
        {variant.headlines.map((h, i) => renderAdItem(h, `h-${vi}-${i}`, i + 1))}
      </div>

      <div className="ad-group">
        <h4>{(variant.platform === 'fb_single_image' || variant.platform === 'fb_video') ? 'Primary Text' : 'Descriptions'}</h4>
        {variant.descriptions.map((d, i) => renderAdItem(d, `d-${vi}-${i}`, i + 1))}
      </div>

      {variant.captions && variant.captions.length > 0 && (
        <div className="ad-group">
          <h4>Captions</h4>
          {variant.captions.map((c, i) => renderAdItem(c, `c-${vi}-${i}`, i + 1))}
        </div>
      )}

      {variant.card_suggestions && variant.card_suggestions.length > 0 && (
        <div className="ad-group">
          <h4>Suggested Card Visuals</h4>
          {variant.card_suggestions.map((s, i) => (
            <div key={`cs-${vi}-${i}`} className="ad-item card-suggestion">
              <span className="ad-index">{i + 1}</span>
              <span className="ad-text">{s}</span>
              <button className="btn-icon" onClick={() => copyToClipboard(s, `cs-${vi}-${i}`)}>
                {copiedId === `cs-${vi}-${i}` ? <CheckCircle size={14} /> : <Copy size={14} />}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );

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
          {data.refinement_count > 0 && (
            <span className="stat-badge refinement">
              <MessageSquare size={13} /> Refined
            </span>
          )}
          <button className="btn btn-sm btn-outline" onClick={downloadCSV}>
            <Download size={14} /> CSV
          </button>
        </div>
      </div>

      {data.variants.map((variant, vi) =>
        variant.platform === 'fb_carousel'
          ? renderCarouselVariant(variant, vi)
          : renderStandardVariant(variant, vi)
      )}

      {/* Feedback / Refinement Section */}
      {onRefine && (
        <div className="feedback-section">
          <div className="feedback-header">
            <MessageSquare size={16} />
            <h4>Refine Results</h4>
          </div>
          <form onSubmit={handleFeedbackSubmit} className="feedback-form">
            <textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder='e.g., "headline 1 for search should not mention discount" or "use sustainable luxury as main keyword"'
              rows={2}
              disabled={refining}
            />
            <button type="submit" className="btn btn-primary btn-sm" disabled={refining || !feedback.trim()}>
              {refining ? 'Refining...' : <><Send size={14} /> Refine</>}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
