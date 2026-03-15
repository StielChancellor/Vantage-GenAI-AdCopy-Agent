import { Zap, Pencil, Sparkles } from 'lucide-react';
import { AD_COPY_FIELD_DEFS, CRM_FIELD_DEFS } from './BriefTracker';

export default function BriefSummaryCard({ brief, mode, onApprove, onEdit, loading }) {
  const fields = mode === 'ad_copy' ? AD_COPY_FIELD_DEFS : CRM_FIELD_DEFS;
  const modeLabel = mode === 'ad_copy' ? 'Ad Copy' : 'CRM Campaign';

  return (
    <div className="brief-summary-card">
      <div className="brief-summary-title">
        <Sparkles size={18} />
        {modeLabel} Brief Summary
      </div>

      <div className="brief-summary-grid">
        {fields.map((field) => {
          const data = brief?.[field.key];
          const value = data?.value;
          const confidence = data?.confidence || 'missing';

          return (
            <div key={field.key} className="brief-summary-field">
              <label>
                {field.label}
                {confidence === 'inferred' && (
                  <span className="inferred-badge">
                    <Sparkles size={10} /> AI Inferred
                  </span>
                )}
              </label>
              <div className={`value ${confidence}`}>
                {value || <span className="not-specified">Not specified</span>}
              </div>
            </div>
          );
        })}
      </div>

      <div className="brief-summary-actions">
        <button className="btn btn-outline btn-sm" onClick={onEdit} disabled={loading}>
          <Pencil size={14} /> Edit Brief
        </button>
        <button className="btn btn-primary btn-sm" onClick={onApprove} disabled={loading}>
          <Zap size={14} /> {loading ? 'Generating...' : 'Approve & Generate'}
        </button>
      </div>
    </div>
  );
}
