import { useState } from 'react';
import { X } from 'lucide-react';

const CONTEXT_TYPES = [
  { value: 'single_property', label: 'Single Property' },
  { value: 'multi_property', label: 'Multi-Property' },
  { value: 'destination', label: 'Destination' },
  { value: 'brand_hq', label: 'Brand HQ' },
];

export default function ContextSelector({ value, onChange }) {
  const [propertyInput, setPropertyInput] = useState('');

  const contextType = value?.context_type || 'single_property';
  const propertyNames = value?.property_names || [];
  const destinationName = value?.destination_name || '';
  const generationMode = value?.generation_mode || 'unified';
  const brandName = value?.brand_name || '';
  const brandTagline = value?.brand_tagline || '';

  const update = (fields) => {
    onChange({ ...value, ...fields });
  };

  const addProperty = (name) => {
    const trimmed = name.trim();
    if (!trimmed) return;
    if (propertyNames.includes(trimmed)) return;
    update({ property_names: [...propertyNames, trimmed] });
    setPropertyInput('');
  };

  const removeProperty = (idx) => {
    update({ property_names: propertyNames.filter((_, i) => i !== idx) });
  };

  const handleTypeChange = (type) => {
    update({
      context_type: type,
      property_names: [],
      destination_name: '',
      brand_name: '',
      brand_tagline: '',
      generation_mode: 'unified',
    });
    setPropertyInput('');
  };

  return (
    <div className="context-selector">
      <div className="form-row">
        <div className="form-group">
          <label>Identity Type</label>
          <select value={contextType} onChange={(e) => handleTypeChange(e.target.value)}>
            {CONTEXT_TYPES.map((ct) => (
              <option key={ct.value} value={ct.value}>{ct.label}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          {contextType === 'single_property' && (
            <>
              <label>Property Name *</label>
              <input
                value={propertyNames[0] || ''}
                onChange={(e) => update({ property_names: [e.target.value] })}
                placeholder="e.g., The Grand Hyatt Mumbai"
              />
            </>
          )}
          {contextType === 'brand_hq' && (
            <>
              <label>Brand Name *</label>
              <input
                value={brandName}
                onChange={(e) => update({ brand_name: e.target.value })}
                placeholder="e.g., Taj Hotels, ITC Hotels"
              />
            </>
          )}
          {contextType === 'destination' && (
            <>
              <label>Destination *</label>
              <input
                value={destinationName}
                onChange={(e) => update({ destination_name: e.target.value })}
                placeholder="e.g., Goa, Rajasthan, Maldives"
              />
            </>
          )}
          {contextType === 'multi_property' && (
            <>
              <label>Properties * <span style={{ fontSize: '0.7rem', fontWeight: 400 }}>(type & Enter)</span></label>
              <div className="url-tags-container" onClick={() => document.getElementById('ctx-prop-input')?.focus()}>
                {propertyNames.map((name, i) => (
                  <div key={i} className="url-tag">
                    <span>{name}</span>
                    <button type="button" onClick={() => removeProperty(i)}><X size={12} /></button>
                  </div>
                ))}
                <input
                  id="ctx-prop-input"
                  className="url-tags-input"
                  value={propertyInput}
                  onChange={(e) => setPropertyInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') { e.preventDefault(); addProperty(propertyInput); }
                    if (e.key === 'Backspace' && propertyInput === '' && propertyNames.length > 0) removeProperty(propertyNames.length - 1);
                  }}
                  placeholder="Add property name..."
                />
              </div>
            </>
          )}
        </div>
      </div>

      {/* Multi-property generation mode */}
      {contextType === 'multi_property' && (
        <div className="form-group">
          <label>Generation Mode</label>
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <label className="radio-label">
              <input type="radio" name="gen-mode" value="unified" checked={generationMode === 'unified'} onChange={() => update({ generation_mode: 'unified' })} />
              Unified (single brand)
            </label>
            <label className="radio-label">
              <input type="radio" name="gen-mode" value="per_property" checked={generationMode === 'per_property'} onChange={() => update({ generation_mode: 'per_property' })} />
              Per-Property (separate)
            </label>
          </div>
        </div>
      )}

      {/* Brand HQ tagline */}
      {contextType === 'brand_hq' && (
        <div className="form-group">
          <label>Brand Tagline <span style={{ fontSize: '0.7rem', fontWeight: 400 }}>(optional)</span></label>
          <input
            value={brandTagline}
            onChange={(e) => update({ brand_tagline: e.target.value })}
            placeholder="e.g., Luxury Redefined"
          />
        </div>
      )}
    </div>
  );
}

// Helper to extract hotel_name from context for backward compat
export function getHotelNameFromContext(context) {
  if (!context) return '';
  const { context_type, property_names = [], destination_name = '', brand_name = '' } = context;
  if (context_type === 'single_property') return property_names[0] || '';
  if (context_type === 'multi_property') return property_names.join(', ');
  if (context_type === 'destination') return destination_name;
  if (context_type === 'brand_hq') return brand_name;
  return '';
}

// Helper to check if context is valid
export function isContextValid(context) {
  if (!context) return false;
  const { context_type, property_names = [], destination_name = '', brand_name = '' } = context;
  if (context_type === 'single_property') return property_names.length > 0 && property_names[0]?.trim();
  if (context_type === 'multi_property') return property_names.length > 0;
  if (context_type === 'brand_hq') return brand_name.trim().length > 0;
  if (context_type === 'destination') return destination_name.trim().length > 0;
  return false;
}
