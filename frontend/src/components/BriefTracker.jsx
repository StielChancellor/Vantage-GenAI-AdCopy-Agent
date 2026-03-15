import { CheckCircle, Circle, CircleDot } from 'lucide-react';

const AD_COPY_FIELD_DEFS = [
  { key: 'identity', label: 'Identity', required: true, prompt: 'Tell me about the property or brand' },
  { key: 'offer_name', label: 'Offer Name', required: true, prompt: 'What is the offer called?' },
  { key: 'inclusions', label: 'Inclusions', required: true, prompt: 'What does the offer include?' },
  { key: 'reference_urls', label: 'Reference URLs', required: true, prompt: 'Share the hotel website URL' },
  { key: 'google_listings', label: 'Google Listings', required: false, prompt: 'Any Google Maps listing?' },
  { key: 'campaign_objective', label: 'Objective', required: false, prompt: 'Is this for awareness, consideration, or conversion?' },
  { key: 'platforms', label: 'Platforms', required: true, prompt: 'Which ad platforms do you want?' },
];

const CRM_FIELD_DEFS = [
  { key: 'identity', label: 'Identity', required: true, prompt: 'Tell me about the property or brand' },
  { key: 'channels', label: 'Channels', required: true, prompt: 'Which channels — WhatsApp, Email, or App Push?' },
  { key: 'campaign_type', label: 'Campaign Type', required: true, prompt: 'What type of campaign is this?' },
  { key: 'target_audience', label: 'Audience', required: true, prompt: 'Who is the target audience?' },
  { key: 'offer_details', label: 'Offer Details', required: true, prompt: 'Describe the offer or promotion' },
  { key: 'tone', label: 'Tone', required: false, prompt: 'What tone — luxurious, formal, casual, or urgent?' },
  { key: 'schedule', label: 'Schedule', required: false, prompt: 'When should the campaign run?' },
  { key: 'events', label: 'Events', required: false, prompt: 'Any events to tie into?' },
];

export { AD_COPY_FIELD_DEFS, CRM_FIELD_DEFS };

export default function BriefTracker({ brief, mode, onFieldClick }) {
  const fields = mode === 'ad_copy' ? AD_COPY_FIELD_DEFS : CRM_FIELD_DEFS;
  const requiredFields = fields.filter((f) => f.required);

  const getStatus = (key) => brief?.[key]?.confidence || 'missing';
  const getValue = (key) => brief?.[key]?.value || null;

  const confirmedOrInferred = requiredFields.filter(
    (f) => getStatus(f.key) === 'confirmed' || getStatus(f.key) === 'inferred'
  ).length;
  const progress = requiredFields.length > 0 ? (confirmedOrInferred / requiredFields.length) * 100 : 0;

  return (
    <div className="brief-tracker">
      <h4 className="brief-tracker-title">Campaign Brief</h4>

      <div className="brief-progress-bar">
        <div className="brief-progress-fill" style={{ width: `${progress}%` }} />
      </div>
      <div className="brief-progress-label">
        {confirmedOrInferred}/{requiredFields.length} required fields
      </div>

      <div className="brief-field-list">
        {fields.map((field) => {
          const status = getStatus(field.key);
          const value = getValue(field.key);

          return (
            <div
              key={field.key}
              className={`brief-field-row ${status}`}
              onClick={() => status === 'missing' && onFieldClick?.(field.prompt)}
              title={status === 'missing' ? 'Click to ask about this' : value || ''}
            >
              <span className={`brief-field-status ${status}`}>
                {status === 'confirmed' && <CheckCircle size={15} />}
                {status === 'inferred' && <CircleDot size={15} />}
                {status === 'missing' && <Circle size={15} />}
              </span>
              <span className={`brief-field-label ${status}`}>
                {field.label}
                {field.required && status === 'missing' && <span className="required-dot">*</span>}
              </span>
              {value && (
                <span className="brief-field-value" title={value}>
                  {value.length > 20 ? value.slice(0, 20) + '…' : value}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
