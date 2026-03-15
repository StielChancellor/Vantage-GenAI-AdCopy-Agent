import { useState } from 'react';
import { Copy, Check, AlertTriangle, AlertCircle } from 'lucide-react';
import toast from 'react-hot-toast';

const CHANNEL_LABELS = {
  whatsapp: 'WhatsApp',
  email: 'Email',
  app_push: 'App Push',
};

const CHANNEL_LIMITS = {
  whatsapp: { max: 1024, strict: true },
  email: { max: 2000, strict: false },
  app_push: { max: 178, strict: false },
};

export default function CRMResults({ content, onRefine, refining }) {
  const [activeChannel, setActiveChannel] = useState(content?.[0]?.channel || 'whatsapp');
  const [feedback, setFeedback] = useState('');
  const [copiedIdx, setCopiedIdx] = useState(null);

  const activeContent = content?.find((c) => c.channel === activeChannel);

  const copyMessage = (msg, idx) => {
    const text = msg.subject ? `${msg.subject}\n\n${msg.body}\n\n${msg.cta}` : `${msg.body}\n\n${msg.cta}`;
    navigator.clipboard.writeText(text).then(() => {
      setCopiedIdx(idx);
      toast.success('Message copied');
      setTimeout(() => setCopiedIdx(null), 2000);
    });
  };

  const handleRefine = (e) => {
    e.preventDefault();
    if (!feedback.trim()) return;
    onRefine(feedback);
    setFeedback('');
  };

  const getCharIndicator = (charCount, channel) => {
    const limit = CHANNEL_LIMITS[channel];
    if (!limit) return null;
    const pct = (charCount / limit.max) * 100;

    if (pct > 100) {
      return limit.strict ? (
        <span className="char-indicator error">
          <AlertCircle size={12} /> {charCount}/{limit.max} — EXCEEDS LIMIT
        </span>
      ) : (
        <span className="char-indicator warning">
          <AlertTriangle size={12} /> {charCount}/{limit.max} — over guidance
        </span>
      );
    }
    return (
      <span className={`char-indicator ${pct > 80 ? 'caution' : 'ok'}`}>
        {charCount}/{limit.max} chars
      </span>
    );
  };

  return (
    <div className="crm-results">
      {/* Channel tabs */}
      <div className="crm-channel-tabs">
        {content?.map((c) => (
          <button
            key={c.channel}
            className={`crm-channel-tab ${activeChannel === c.channel ? 'active' : ''} channel-${c.channel}`}
            onClick={() => setActiveChannel(c.channel)}
          >
            {CHANNEL_LABELS[c.channel] || c.channel}
            {c.warnings?.length > 0 && <span className="warning-dot" />}
          </button>
        ))}
      </div>

      {/* Messages */}
      {activeContent && (
        <div className="crm-messages">
          {activeContent.warnings?.length > 0 && (
            <div className="crm-warnings">
              {activeContent.warnings.map((w, i) => (
                <div key={i} className="crm-warning">
                  <AlertTriangle size={14} /> {w}
                </div>
              ))}
            </div>
          )}

          {activeContent.messages?.map((msg, i) => (
            <div key={i} className="crm-message-card">
              <div className="crm-message-header">
                <span className="crm-message-label">Variant {i + 1}</span>
                <div className="crm-message-meta">
                  {getCharIndicator(msg.char_count || 0, activeChannel)}
                  <button
                    className="btn-icon"
                    onClick={() => copyMessage(msg, i)}
                    title="Copy message"
                  >
                    {copiedIdx === i ? <Check size={14} /> : <Copy size={14} />}
                  </button>
                </div>
              </div>

              {msg.headline && (
                <div className="crm-message-headline">
                  <span className="crm-field-label">Headline:</span> {msg.headline}
                </div>
              )}

              {msg.subject && (
                <div className="crm-message-subject">
                  <span className="crm-field-label">Subject:</span> {msg.subject}
                </div>
              )}

              <div className="crm-message-body">{msg.body}</div>

              {msg.cta && (
                <div className="crm-message-cta">
                  <span className="crm-field-label">CTA:</span> {msg.cta}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Refinement */}
      <div className="crm-refinement">
        <form onSubmit={handleRefine}>
          <textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Provide feedback to refine the CRM content..."
            rows={3}
            disabled={refining}
          />
          <button type="submit" className="btn btn-primary" disabled={refining || !feedback.trim()}>
            {refining ? 'Refining...' : 'Refine Content'}
          </button>
        </form>
      </div>
    </div>
  );
}
