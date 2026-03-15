import { useState } from 'react';
import { X } from 'lucide-react';

const CONTEXT_TYPES = [
  { value: 'single_property', label: 'Single Property', desc: 'One hotel/property' },
  { value: 'multi_property', label: 'Multi-Property', desc: 'Multiple properties' },
  { value: 'destination', label: 'Destination', desc: 'Location/cluster' },
  { value: 'brand_hq', label: 'Brand HQ', desc: 'Brand-wide campaign' },
];

export default function ContextSelector({ value, onChange }) {
  const [propertyInput, setPropertyInput] = useState('');

  const contextType = value?.context_type || 'single_property';
  const propertyNames = value?.property_names || [];
  const destinationName = value?.destination_name || '';
  const generationMode = value?.generation_mode || 'unified';

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
    // Reset fields when type changes
    update({
      context_type: type,
      property_names: [],
      destination_name: '',
      generation_mode: 'unified',
    });
    setPropertyInput('');
  };

  // Derive hotel_name for backward compat
  const getHotelName = () => {
    if (contextType === 'single_property') return propertyNames[0] || '';
    if (contextType === 'destination') return destinationName;
    return propertyNames.join(', ');
  };

  const isValid = () => {
    if (contextType === 'single_property') return propertyNames.length > 0;
    if (contextType === 'multi_property' || contextType === 'brand_hq') return propertyNames.length > 0;
    if (contextType === 'destination') return destinationName.trim().length > 0;
    return false;
  };

  return (
    <div className="context-selector">
      <label>Identity</label>
      <div className="context-type-grid">
        {CONTEXT_TYPES.map((ct) => (
          <button
            key={ct.value}
            type="button"
            className={`context-type-card ${contextType === ct.value ? 'active' : ''}`}
            onClick={() => handleTypeChange(ct.value)}
          >
            <span className="context-type-label">{ct.label}</span>
            <span className="context-type-desc">{ct.desc}</span>
          </button>
        ))}
      </div>

      {/* Single Property */}
      {contextType === 'single_property' && (
        <div className="form-group" style={{ marginTop: '0.75rem' }}>
          <label>Property Name *</label>
          <input
            value={propertyNames[0] || ''}
            onChange={(e) => update({ property_names: [e.target.value] })}
            placeholder="e.g., The Grand Hyatt Mumbai"
          />
        </div>
      )}

      {/* Multi-Property / Brand HQ — tag-based input */}
      {(contextType === 'multi_property' || contextType === 'brand_hq') && (
        <>
          <div className="form-group" style={{ marginTop: '0.75rem' }}>
            <label>Properties * <span style={{ fontSize: '0.7rem', fontWeight: 400 }}>(type name & press Enter)</span></label>
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
          </div>

          <div className="form-group">
            <label>Generation Mode</label>
            <div className="checkbox-grid">
              <label className="radio-label">
                <input type="radio" name="gen-mode" value="unified" checked={generationMode === 'unified'} onChange={() => update({ generation_mode: 'unified' })} />
                Unified (single brand campaign)
              </label>
              <label className="radio-label">
                <input type="radio" name="gen-mode" value="per_property" checked={generationMode === 'per_property'} onChange={() => update({ generation_mode: 'per_property' })} />
                Per-Property (separate for each)
              </label>
            </div>
          </div>
        </>
      )}

      {/* Destination */}
      {contextType === 'destination' && (
        <div className="form-group" style={{ marginTop: '0.75rem' }}>
          <label>Destination Name *</label>
          <input
            value={destinationName}
            onChange={(e) => update({ destination_name: e.target.value })}
            placeholder="e.g., Goa, Rajasthan, Maldives"
          />
        </div>
      )}
    </div>
  );
}

// Helper to extract hotel_name from context for backward compat
export function getHotelNameFromContext(context) {
  if (!context) return '';
  const { context_type, property_names = [], destination_name = '' } = context;
  if (context_type === 'single_property') return property_names[0] || '';
  if (context_type === 'destination') return destination_name;
  return property_names.join(', ');
}

// Helper to check if context is valid
export function isContextValid(context) {
  if (!context) return false;
  const { context_type, property_names = [], destination_name = '' } = context;
  if (context_type === 'single_property') return property_names.length > 0 && property_names[0]?.trim();
  if (context_type === 'multi_property' || context_type === 'brand_hq') return property_names.length > 0;
  if (context_type === 'destination') return destination_name.trim().length > 0;
  return false;
}
