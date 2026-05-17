/**
 * CampaignIdeation v2.8 — Form → Directions → Iterate → Final 10 → Handoff.
 *
 * Step 1 (Brief)     — structured inputs: offer, inclusions, discount,
 *                      hotels (list or natural-language phrase), audience
 *                      slider, tone slider. Loyalty pill auto-resolves.
 * Step 2 (Directions)— 3–5 distinct creative directions, each with 5 names.
 *                      User picks a direction OR types a steer + iterates.
 * Step 3 (Final 10)  — exactly 10 polished concepts with visual cue chips.
 *                      Click one → finalise. Check multiple + steer → merge.
 * Step 4 (Handoff)   — redirect to /unified with hotels pre-filled.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  Sparkles, ChevronLeft, ChevronRight, Loader2, X as XIcon,
  RefreshCcw, CheckCircle2, Plus, Wand2,
} from 'lucide-react';
import IntelligentPropertyPicker from '../components/IntelligentPropertyPicker';
import { useSelection } from '../contexts/SelectionContext';
import { useAuth } from '../hooks/useAuth';
import {
  startIdeation, resolveHotels, generateDirections, refineIdeation,
  finalizeIdeation, chooseShortlist,
} from '../services/api';

const STEPS = [
  { id: 1, label: 'Brief' },
  { id: 2, label: 'Directions' },
  { id: 3, label: 'Final 10' },
  { id: 4, label: 'Done' },
];

const DISCOUNT_KINDS = [
  { value: 'percent_off',  label: '% off' },
  { value: 'flat_amount',  label: 'Flat amount' },
  { value: 'bogo',         label: 'Buy 1 get 1' },
  { value: 'free_upgrade', label: 'Free upgrade' },
  { value: 'no_discount',  label: 'No discount' },
];

const AUDIENCE_STOPS = [
  { value: 'business',   label: 'Business' },
  { value: 'in_between', label: 'In-between' },
  { value: 'leisure',    label: 'Leisure' },
];

const TONE_STOPS = [
  { value: 'tactical',     label: 'Tactical', hint: 'Easy-to-relate, offer-led' },
  { value: 'hybrid',       label: 'Hybrid',   hint: 'Lyrical but anchored to the offer' },
  { value: 'aspirational', label: 'Aspirational', hint: 'Thought-provoking, emotion-evoking' },
];

// ── Inputs from the IntelligentPropertyPicker → resolution shape ──
function resolutionFromPicker(p) {
  if (!p) return { mode: 'list', resolved_hotel_ids: [], resolved_brand_ids: [], is_loyalty: false };
  return {
    mode: 'list',
    phrase: '',
    resolved_hotel_ids: p.hotel_ids || [],
    resolved_brand_ids: p.brand_ids || [],
    is_loyalty: !!p.is_loyalty,
  };
}

function hotelChipLabel(h) {
  const bits = [h.name];
  if (h.brand) bits.push(h.brand);
  if (h.city)  bits.push(h.city);
  return bits.filter(Boolean).join(' · ');
}

// ── Small UI atoms ───────────────────────────────────────────────────

function ToneSlider({ value, onChange, stops, label }) {
  const idx = stops.findIndex((s) => s.value === value);
  return (
    <div className="form-group">
      <label>{label}</label>
      <input
        type="range"
        min={0}
        max={stops.length - 1}
        value={idx < 0 ? 0 : idx}
        onChange={(e) => onChange(stops[Number(e.target.value)].value)}
        style={{ width: '100%' }}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--em-ink-soft)' }}>
        {stops.map((s) => (
          <span
            key={s.value}
            style={{
              fontWeight: s.value === value ? 700 : 400,
              color: s.value === value ? 'var(--em-ink)' : 'var(--em-ink-soft)',
            }}
          >
            {s.label}
          </span>
        ))}
      </div>
      {stops.find((s) => s.value === value)?.hint && (
        <p style={{ fontSize: 12, color: 'var(--em-ink-soft)', marginTop: 4 }}>
          {stops.find((s) => s.value === value).hint}
        </p>
      )}
    </div>
  );
}

function PaletteSwatch({ token }) {
  // Best-effort color inference from common palette tokens. Falls back to a
  // neutral chip if the token isn't recognised.
  const swatchColor = inferSwatch(token);
  return (
    <span className="cue-chip palette-chip" title={token}>
      <span className="palette-swatch" style={{ background: swatchColor }} />
      {token}
    </span>
  );
}

function inferSwatch(tok) {
  const t = String(tok || '').toLowerCase();
  // Pre-baked map for common evocative tokens.
  const map = {
    mist:'#D8E2DC', slate:'#3F4C4F', moss:'#5C6B5A', ivory:'#F5EFE6',
    ochre:'#C99B57', sand:'#D9B382', linen:'#E8E0D3', amber:'#C28A3F',
    teal:'#356A77', cobalt:'#1F3B6E', rose:'#C99097', plum:'#5A3050',
    saffron:'#E2A937', emerald:'#2C715A', stone:'#88827A', pine:'#33502E',
    sage:'#9CAB8A', cream:'#F0E9DD', clay:'#B07A5A', smoke:'#7F8A8C',
    midnight:'#101428', sunset:'#C6604D', salt:'#EDEDEB', shore:'#A8B8B0',
    fog:'#C8CFD4', bronze:'#A06F3A', ruby:'#73223A', jade:'#3D8B71',
  };
  // Hex passthrough.
  const hexMatch = t.match(/#?[0-9a-f]{6}\b/);
  if (hexMatch) return hexMatch[0].startsWith('#') ? hexMatch[0] : '#' + hexMatch[0];
  for (const k of Object.keys(map)) if (t.includes(k)) return map[k];
  return '#D4CFC2';
}

function CueChip({ label, value }) {
  if (!value) return null;
  return (
    <span className="cue-chip">
      <span className="cue-chip-label">{label}</span>
      <span className="cue-chip-value">{value}</span>
    </span>
  );
}

function VisualCueRow({ cue }) {
  if (!cue) return null;
  return (
    <div className="visual-cue">
      {(cue.palette || []).map((p, i) => <PaletteSwatch key={`p${i}`} token={p} />)}
      {(cue.motifs || []).map((m, i) => (
        <span key={`m${i}`} className="cue-chip"><span className="cue-chip-label">motif</span><span className="cue-chip-value">{m}</span></span>
      ))}
      <CueChip label="mood" value={cue.mood} />
      <CueChip label="photo" value={cue.photography_style} />
      <CueChip label="logo" value={cue.logo_placement} />
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────

export default function CampaignIdeation() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { selection: sharedSelection, setSelection: setSharedSelection } = useSelection();

  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [llmLoading, setLlmLoading] = useState(false);

  // ── Step 1 form state ────────────────────────────────
  const [offerName, setOfferName]     = useState('');
  const [inclusions, setInclusions]   = useState('');
  const [discountKind, setDiscountKind] = useState('percent_off');
  const [discountValue, setDiscountValue] = useState('');
  const [audienceAxis, setAudienceAxis] = useState('in_between');
  const [toneAxis, setToneAxis] = useState('hybrid');

  // Hotels — tabbed (list / phrase). Resolution lives in `resolution`.
  const [hotelsMode, setHotelsMode] = useState('list');     // 'list' | 'phrase'
  const [pickerSel,  setPickerSel]  = useState(sharedSelection || null);
  const [phrase,     setPhrase]     = useState('');
  const [resolution, setResolution] = useState({
    mode: 'list',
    phrase: '',
    resolved_hotel_ids: [],
    resolved_brand_ids: [],
    is_loyalty: false,
    matched: [],
    notes: '',
  });
  const [resolving, setResolving] = useState(false);

  // Sync picker → resolution.
  useEffect(() => {
    if (hotelsMode !== 'list') return;
    const r = resolutionFromPicker(pickerSel);
    setResolution((prev) => ({ ...prev, ...r, matched: (pickerSel?._labels?.hotels || []).map((h) => ({
      hotel_id: h.id, name: h.label, brand: h.brand || '', city: '',
    })) }));
  }, [pickerSel, hotelsMode]);

  const onResolvePhrase = async () => {
    if (!phrase.trim()) return toast.error('Type a phrase like "all hill hotels in north India".');
    setResolving(true);
    try {
      const r = await resolveHotels(phrase.trim());
      const d = r.data || {};
      setResolution({
        mode: 'phrase',
        phrase: phrase.trim(),
        resolved_hotel_ids: d.resolved_hotel_ids || [],
        resolved_brand_ids: d.resolved_brand_ids || [],
        is_loyalty: !!d.is_loyalty,
        matched: d.matched || [],
        notes: d.notes || '',
      });
      if (!d.matched?.length) toast.error('No hotels matched. Try a different phrase or switch to List mode.');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Resolver failed.');
    } finally {
      setResolving(false);
    }
  };

  const removeHotelChip = (hotelId) => {
    setResolution((r) => ({
      ...r,
      resolved_hotel_ids: r.resolved_hotel_ids.filter((id) => id !== hotelId),
      matched: r.matched.filter((m) => m.hotel_id !== hotelId),
    }));
  };

  const setupValid = (
    offerName.trim().length >= 3 &&
    resolution.resolved_hotel_ids.length + resolution.resolved_brand_ids.length > 0 &&
    (discountKind === 'no_discount' || discountKind === 'free_upgrade' || discountValue.trim().length > 0)
  );

  // ── Step 2+3 state ───────────────────────────────────
  const [ideationId, setIdeationId] = useState('');
  const [iterations, setIterations] = useState([]);     // mirrors backend `iterations`
  const [directionsBatch, setDirectionsBatch] = useState(null); // latest IdeationDirectionsResponse
  const [selectedDirectionId, setSelectedDirectionId] = useState(null);
  const [selectedConceptIds,  setSelectedConceptIds]  = useState([]);
  const [steerText, setSteerText] = useState('');
  const [finalBatch, setFinalBatch] = useState(null);  // latest IdeationFinalResponse
  const [finalSelected, setFinalSelected] = useState([]);
  const [mergeSteer, setMergeSteer] = useState('');
  const [chosenIndex, setChosenIndex] = useState(null);

  const inputsPayload = useMemo(() => ({
    offer_name: offerName.trim(),
    inclusions: inclusions.trim(),
    discount: { kind: discountKind, value: discountValue.trim() },
    audience_axis: audienceAxis,
    tone_axis: toneAxis,
    hotels_resolution: {
      mode: resolution.mode,
      phrase: resolution.phrase,
      resolved_hotel_ids: resolution.resolved_hotel_ids,
      resolved_brand_ids: resolution.resolved_brand_ids,
      is_loyalty: !!resolution.is_loyalty,
    },
  }), [offerName, inclusions, discountKind, discountValue, audienceAxis, toneAxis, resolution]);

  const onStart = async () => {
    if (!setupValid) {
      toast.error('Offer, hotels, and (where applicable) a discount value are required.');
      return;
    }
    setLoading(true);
    try {
      const r = await startIdeation(inputsPayload);
      const id = r.data?.ideation_id;
      setIdeationId(id);
      // mirror picker selection into shared context for downstream tools.
      if (hotelsMode === 'list' && pickerSel) setSharedSelection(pickerSel);
      setLlmLoading(true);
      const dr = await generateDirections(id);
      const d = dr.data || {};
      setDirectionsBatch(d);
      setIterations([d]);
      setStep(2);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not start ideation.');
    } finally {
      setLoading(false);
      setLlmLoading(false);
    }
  };

  const onIterateAgain = async (pickWhole) => {
    if (!ideationId) return;
    setLlmLoading(true);
    try {
      const body = {
        selected_direction_id: pickWhole || selectedDirectionId || null,
        selected_concept_ids: selectedConceptIds,
        freetext_steer: steerText.trim(),
      };
      const r = await refineIdeation(ideationId, body);
      const d = r.data || {};
      setDirectionsBatch(d);
      setIterations((prev) => [...prev, d]);
      setSelectedDirectionId(null);
      setSelectedConceptIds([]);
      setSteerText('');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Refinement failed.');
    } finally {
      setLlmLoading(false);
    }
  };

  const onGenerateFinal10 = async () => {
    if (!ideationId) return;
    setLlmLoading(true);
    try {
      const body = {
        seed_concept_ids: selectedConceptIds.length > 0 ? selectedConceptIds : [],
        freetext_steer: steerText.trim(),
      };
      const r = await finalizeIdeation(ideationId, body);
      setFinalBatch(r.data || {});
      setFinalSelected([]);
      setStep(3);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Final-10 generation failed.');
    } finally {
      setLlmLoading(false);
    }
  };

  const onRegenerateFinal = async () => {
    if (!ideationId) return;
    setLlmLoading(true);
    try {
      const body = {
        seed_concept_ids: finalSelected.map((i) => finalBatch?.concepts?.[i]?.id).filter(Boolean),
        freetext_steer: mergeSteer.trim(),
      };
      const r = await finalizeIdeation(ideationId, body);
      setFinalBatch(r.data || {});
      setFinalSelected([]);
      setMergeSteer('');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Regeneration failed.');
    } finally {
      setLlmLoading(false);
    }
  };

  const onFinalize = async () => {
    if (!ideationId || finalSelected.length !== 1) return;
    const idx = finalSelected[0];
    setLoading(true);
    try {
      const r = await chooseShortlist(ideationId, idx);
      setChosenIndex(idx);
      const ucid = r.data?.unified_campaign_id;
      setStep(4);
      if (ucid) setTimeout(() => navigate(`/unified?campaign_id=${ucid}`), 1200);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not finalise concept.');
    } finally {
      setLoading(false);
    }
  };

  // ── Render ───────────────────────────────────────────
  const scopeSummary = user?.scope_summary || null;
  const headerSummary = useMemo(() => {
    if (!resolution.resolved_hotel_ids.length && !resolution.resolved_brand_ids.length) return '—';
    const bits = [];
    if (resolution.is_loyalty) bits.push('Club ITC (Loyalty)');
    if (resolution.resolved_brand_ids.length) bits.push(`${resolution.resolved_brand_ids.length} brand${resolution.resolved_brand_ids.length > 1 ? 's' : ''}`);
    if (resolution.resolved_hotel_ids.length) bits.push(`${resolution.resolved_hotel_ids.length} hotel${resolution.resolved_hotel_ids.length > 1 ? 's' : ''}`);
    return bits.join(' · ');
  }, [resolution]);

  return (
    <div className="page-shell">
      <header className="page-header">
        <div className="page-title-row">
          <Sparkles size={20} />
          <h1>Campaign Ideation</h1>
        </div>
        <p className="page-subtitle">
          Describe the offer, agree the angle, pick the concept. The agent acts as a senior creative director.
        </p>
      </header>

      <div className="wizard-steps">
        {STEPS.map((s) => (
          <div key={s.id} className={`wizard-step ${step === s.id ? 'active' : ''} ${step > s.id ? 'done' : ''}`}>
            <div className="wizard-step-num">{s.id}</div>
            <div className="wizard-step-label">{s.label}</div>
          </div>
        ))}
      </div>

      {step === 1 && (
        <section className="wizard-panel">
          <h2>Brief</h2>

          <div className="brief-form-grid">
            <div className="form-group">
              <label>Offer name *</label>
              <input
                type="text"
                placeholder='e.g., "Monsoon Soiree"'
                value={offerName}
                onChange={(e) => setOfferName(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label>Inclusions</label>
              <textarea
                rows={3}
                placeholder="What does the offer include? E.g. breakfast, spa credit, late checkout."
                value={inclusions}
                onChange={(e) => setInclusions(e.target.value)}
              />
            </div>

            <div className="form-row">
              <div className="form-group" style={{ flex: 1 }}>
                <label>Discount</label>
                <select value={discountKind} onChange={(e) => setDiscountKind(e.target.value)}>
                  {DISCOUNT_KINDS.map((d) => (
                    <option key={d.value} value={d.value}>{d.label}</option>
                  ))}
                </select>
              </div>
              {discountKind !== 'no_discount' && discountKind !== 'free_upgrade' && (
                <div className="form-group" style={{ flex: 1 }}>
                  <label>Value *</label>
                  <input
                    type="text"
                    placeholder={discountKind === 'percent_off' ? 'e.g. 25%' : 'e.g. ₹3000'}
                    value={discountValue}
                    onChange={(e) => setDiscountValue(e.target.value)}
                  />
                </div>
              )}
            </div>

            <div className="form-group">
              <label>Participating hotels *</label>
              <div className="hotels-tabs">
                <button
                  type="button"
                  className={`tab-btn ${hotelsMode === 'list' ? 'active' : ''}`}
                  onClick={() => setHotelsMode('list')}
                >
                  Pick from list
                </button>
                <button
                  type="button"
                  className={`tab-btn ${hotelsMode === 'phrase' ? 'active' : ''}`}
                  onClick={() => setHotelsMode('phrase')}
                >
                  Describe in words
                </button>
              </div>

              {hotelsMode === 'list' && (
                <IntelligentPropertyPicker
                  value={pickerSel}
                  onChange={setPickerSel}
                  scopeSummary={scopeSummary}
                />
              )}

              {hotelsMode === 'phrase' && (
                <>
                  <textarea
                    rows={2}
                    placeholder='e.g., "all hill hotels in north India", or "all coastal properties under Welcomhotel"'
                    value={phrase}
                    onChange={(e) => setPhrase(e.target.value)}
                  />
                  <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                    <button
                      type="button"
                      className="btn btn-outline btn-sm"
                      onClick={onResolvePhrase}
                      disabled={resolving || !phrase.trim()}
                    >
                      {resolving ? <Loader2 size={14} className="spin" /> : <Wand2 size={14} />}
                      Resolve to hotels
                    </button>
                    {resolution.notes && (
                      <span style={{ fontSize: 12, color: 'var(--em-ink-soft)', alignSelf: 'center' }}>
                        {resolution.notes}
                      </span>
                    )}
                  </div>
                </>
              )}

              {resolution.matched.length > 0 && (
                <div className="hotel-chips">
                  {resolution.matched.map((h) => (
                    <span key={h.hotel_id} className="hotel-chip">
                      {hotelChipLabel(h)}
                      <button type="button" onClick={() => removeHotelChip(h.hotel_id)} className="hotel-chip-x">
                        <XIcon size={12} />
                      </button>
                    </span>
                  ))}
                </div>
              )}

              {resolution.is_loyalty && (
                <p className="loyalty-pill"><Sparkles size={12} /> Loyalty mode — visual cues anonymised across partner brands.</p>
              )}
            </div>

            <ToneSlider
              label="Audience *"
              value={audienceAxis}
              onChange={setAudienceAxis}
              stops={AUDIENCE_STOPS}
            />
            <ToneSlider
              label="Tone *"
              value={toneAxis}
              onChange={setToneAxis}
              stops={TONE_STOPS}
            />
          </div>

          <div className="wizard-nav">
            <div className="wizard-nav-spacer" />
            <button className="btn btn-primary" onClick={onStart} disabled={!setupValid || loading || llmLoading}>
              {loading || llmLoading ? <Loader2 size={16} className="spin" /> : <Sparkles size={16} />}
              Start ideating
            </button>
          </div>
        </section>
      )}

      {step === 2 && directionsBatch && (
        <section className="wizard-panel">
          <div className="step-header">
            <div>
              <h2 style={{ margin: 0 }}>Directions</h2>
              <p style={{ margin: '4px 0 0', color: 'var(--em-ink-soft)' }}>
                {headerSummary} · Iteration {directionsBatch.iteration} · {directionsBatch.directions?.length || 0} directions
              </p>
            </div>
            <button className="btn btn-outline btn-sm" onClick={() => setStep(1)}>
              <ChevronLeft size={14} /> Back to brief
            </button>
          </div>

          {llmLoading && <div className="loading-banner"><Loader2 size={16} className="spin" /> Reasoning…</div>}

          <div className="direction-grid">
            {(directionsBatch.directions || []).map((d) => (
              <article
                key={d.id}
                className={`direction-card ${selectedDirectionId === d.id ? 'selected' : ''}`}
              >
                <header>
                  <h3>{d.title}</h3>
                  <p className="direction-rationale">{d.rationale}</p>
                </header>

                <VisualCueRow cue={d.visual_cue} />

                <ul className="concept-list">
                  {(d.concepts || []).map((c) => {
                    const isSel = selectedConceptIds.includes(c.id);
                    return (
                      <li
                        key={c.id}
                        className={`concept-row ${isSel ? 'selected' : ''}`}
                        onClick={() => setSelectedConceptIds((prev) =>
                          isSel ? prev.filter((x) => x !== c.id) : [...prev, c.id]
                        )}
                      >
                        <div className="concept-name">{c.name}</div>
                        <div className="concept-just">{c.justification}</div>
                      </li>
                    );
                  })}
                </ul>

                <footer>
                  <button
                    type="button"
                    className="btn btn-outline btn-sm"
                    onClick={() => onIterateAgain(d.id)}
                    disabled={llmLoading}
                  >
                    <ChevronRight size={14} /> Push further in this direction
                  </button>
                </footer>
              </article>
            ))}
          </div>

          <div className="refine-bar">
            <textarea
              rows={2}
              placeholder='Optional: type a steer ("more Welcomgreen angle", "less corporate")…'
              value={steerText}
              onChange={(e) => setSteerText(e.target.value)}
            />
            <div className="refine-bar-row">
              <span style={{ fontSize: 12, color: 'var(--em-ink-soft)' }}>
                {selectedConceptIds.length > 0
                  ? `${selectedConceptIds.length} concept${selectedConceptIds.length > 1 ? 's' : ''} selected as seeds`
                  : 'Tap any concept to seed the next iteration'}
              </span>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  type="button"
                  className="btn btn-outline"
                  onClick={() => onIterateAgain(null)}
                  disabled={llmLoading}
                >
                  {llmLoading ? <Loader2 size={14} className="spin" /> : <RefreshCcw size={14} />}
                  Iterate again
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={onGenerateFinal10}
                  disabled={llmLoading}
                >
                  {llmLoading ? <Loader2 size={14} className="spin" /> : <Sparkles size={14} />}
                  Generate Final 10
                </button>
              </div>
            </div>
          </div>
        </section>
      )}

      {step === 3 && finalBatch && (
        <section className="wizard-panel">
          <div className="step-header">
            <div>
              <h2 style={{ margin: 0 }}>Final 10</h2>
              <p style={{ margin: '4px 0 0', color: 'var(--em-ink-soft)' }}>
                {headerSummary} · Pick one to finalise, or check multiple to merge.
              </p>
            </div>
            <button className="btn btn-outline btn-sm" onClick={() => setStep(2)}>
              <ChevronLeft size={14} /> Back to directions
            </button>
          </div>

          {llmLoading && <div className="loading-banner"><Loader2 size={16} className="spin" /> Reasoning…</div>}

          <div className="final-grid">
            {(finalBatch.concepts || []).map((c, i) => {
              const isSel = finalSelected.includes(i);
              return (
                <article
                  key={c.id || i}
                  className={`final-card ${isSel ? 'final-card-selected' : ''}`}
                  onClick={() => setFinalSelected((prev) => isSel ? prev.filter((x) => x !== i) : [...prev, i])}
                >
                  <header>
                    <span className="final-card-num">#{i + 1}</span>
                    <input
                      type="checkbox"
                      checked={isSel}
                      onChange={() => { /* handled by row click */ }}
                      onClick={(e) => e.stopPropagation()}
                      className="em-switcher-check"
                    />
                  </header>
                  <h3>{c.name}</h3>
                  <p className="final-justification">{c.justification}</p>
                  <VisualCueRow cue={c.visual_cue} />
                </article>
              );
            })}
          </div>

          <div className="final-action-bar">
            {finalSelected.length === 0 && (
              <p className="muted">Pick one to finalise — or check multiple to merge into something new.</p>
            )}
            {finalSelected.length === 1 && (
              <button className="btn btn-primary" onClick={onFinalize} disabled={loading}>
                {loading ? <Loader2 size={16} className="spin" /> : <CheckCircle2 size={16} />}
                Finalise concept #{finalSelected[0] + 1}
              </button>
            )}
            {finalSelected.length > 1 && (
              <div className="merge-steer">
                <textarea
                  rows={2}
                  placeholder='Optional steer for the merge ("combine #2 visual with #7 name energy")'
                  value={mergeSteer}
                  onChange={(e) => setMergeSteer(e.target.value)}
                />
                <div className="merge-row">
                  <span style={{ fontSize: 12, color: 'var(--em-ink-soft)' }}>
                    {finalSelected.length} concepts selected as seeds — Regenerate gives a fresh batch of 10.
                  </span>
                  <button className="btn btn-primary" onClick={onRegenerateFinal} disabled={llmLoading}>
                    {llmLoading ? <Loader2 size={14} className="spin" /> : <RefreshCcw size={14} />}
                    Regenerate 10 with these as seeds
                  </button>
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {step === 4 && (
        <section className="wizard-panel">
          <div className="em-card" style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <CheckCircle2 size={32} color="var(--primary)" />
            <h2 style={{ margin: 0 }}>Draft campaign created</h2>
            <p style={{ color: 'var(--em-ink-soft)', margin: 0 }}>
              Opening the Unified Campaign editor with your selected concept prefilled…
            </p>
          </div>
        </section>
      )}
    </div>
  );
}
