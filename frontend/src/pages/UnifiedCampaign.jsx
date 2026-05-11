/**
 * Unified Campaign — single brief that explodes into multi-channel,
 * multi-property ad copy (v2.6).
 *
 * 5-step wizard:
 *   1. Brief         → free-form text + reference URLs
 *   2. Finalize      → Gemini-structured fields, editable, then LOCK
 *   3. Events        → optional, reuses EventCalendar (skippable)
 *   4. Properties + Channels + Levels → IntelligentPropertyPicker + checkboxes
 *   5. Generate      → orchestrator returns per-(entity × channel × level) variants
 *
 * Locked campaigns are editable later via My Account → Unified Briefs.
 */
import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  Zap, ChevronLeft, ChevronRight, Lock, Unlock, Search, X, Download, Sparkles,
} from 'lucide-react';
import {
  createCampaign, getCampaign, patchCampaign, lockCampaign, unlockCampaign,
  generateCampaign, searchEvents,
} from '../services/api';
import IntelligentPropertyPicker from '../components/IntelligentPropertyPicker';
import EventCalendar from '../components/EventCalendar';
import GenerationProgress from '../components/GenerationProgress';
import { useSelection } from '../contexts/SelectionContext';

const STEPS = [
  { num: 1, label: 'Brief' },
  { num: 2, label: 'Finalize' },
  { num: 3, label: 'Events' },
  { num: 4, label: 'Properties & Channels' },
  { num: 5, label: 'Generate' },
];

const CHANNELS = [
  { id: 'search_ads', label: 'Search Ads' },
  { id: 'meta_ads',   label: 'Meta Ads (FB / IG)' },
  { id: 'app_push',   label: 'App Push Notification' },
];

const LEVELS = [
  { id: 'chain',              label: 'Chain (brand-level)' },
  { id: 'single',             label: 'Single property' },
  { id: 'chain_plus_single',  label: 'Chain + per-property' },
];

function emptyStructured() {
  return {
    campaign_name: '', start_date: '', end_date: '',
    booking_window_start: '', booking_window_end: '',
    cancellation_policy: '', inclusions: '', promo_code: '',
    landing_page_url: '', participating_hotels: [],
    brand_ids: [], cities: [],
    target_audience: '', summary: '',
  };
}

export default function UnifiedCampaign() {
  const location = useLocation();
  const navigate = useNavigate();
  const { setSelection: setSharedSelection } = useSelection();
  const queryId = useMemo(() => new URLSearchParams(location.search).get('campaign') || '', [location.search]);

  const [step, setStep] = useState(1);
  const [campaign, setCampaign] = useState(null);       // server doc
  const [raw, setRaw] = useState('');
  const [refUrlInput, setRefUrlInput] = useState('');
  const [refUrls, setRefUrls] = useState([]);
  const [structured, setStructured] = useState(emptyStructured());
  const [events, setEvents] = useState([]);
  const [eventResults, setEventResults] = useState([]);
  const [searchingEvents, setSearchingEvents] = useState(false);
  const [markets, setMarkets] = useState(['India']);
  const [dateRangeStart, setDateRangeStart] = useState('');
  const [dateRangeEnd, setDateRangeEnd] = useState('');

  const [pickerSel, setPickerSel] = useState(null);
  const [levelsSel, setLevelsSel] = useState(['single']);
  const [channelsSel, setChannelsSel] = useState(['search_ads']);

  const [generating, setGenerating] = useState(false);
  const [results, setResults] = useState([]);
  const [submitting, setSubmitting] = useState(false);

  const isLocked = campaign?.status === 'locked';

  // Hydrate if we landed from /unified?campaign=<id> (edit-from-MyAccount path).
  useEffect(() => {
    if (!queryId) return;
    (async () => {
      try {
        const r = await getCampaign(queryId);
        const c = r.data;
        setCampaign(c);
        setRaw(c.raw_brief || '');
        setRefUrls(c.reference_urls || []);
        setStructured({ ...emptyStructured(), ...(c.structured || {}) });
        setEvents(c.events || []);
        setResults(c.generated || []);
        if (c.selection) {
          const s = c.selection;
          setLevelsSel(s.campaign_levels || ['single']);
          setChannelsSel(s.channels || ['search_ads']);
          setPickerSel({
            scope: s.scope,
            hotel_ids: s.hotel_ids || [],
            brand_ids: s.brand_ids || [],
            cities: s.cities || [],
            is_loyalty: !!s.is_loyalty,
            _labels: { hotels: [], brands: [], cities: [] },
          });
        }
        setStep(c.status === 'locked' ? 2 : 2);
      } catch {
        toast.error('Could not load the campaign.');
      }
    })();
  }, [queryId]);

  // ── step 1 → step 2 (structure + persist) ─────────────────────────
  const submitBrief = async () => {
    if (!raw.trim()) { toast.error('Type at least a short brief to start.'); return; }
    setSubmitting(true);
    try {
      const r = await createCampaign({ raw_brief: raw, reference_urls: refUrls });
      setCampaign(r.data);
      setStructured({ ...emptyStructured(), ...(r.data.structured || {}) });
      setStep(2);
      toast.success('Brief structured. Review and lock it.');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not structure the brief.');
    } finally {
      setSubmitting(false);
    }
  };

  // ── step 2 patches + lock ────────────────────────────────────────
  const saveStructured = async () => {
    if (!campaign) return;
    try {
      const r = await patchCampaign(campaign.id, { structured });
      setCampaign(r.data);
      toast.success('Saved.');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Save failed.');
    }
  };
  const lockAndContinue = async () => {
    if (!campaign) return;
    if (!structured.campaign_name?.trim()) { toast.error('Campaign name is required.'); return; }
    setSubmitting(true);
    try {
      await patchCampaign(campaign.id, { structured });
      const r = await lockCampaign(campaign.id);
      setCampaign(r.data);
      setStep(3);
      toast.success('Campaign locked.');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Lock failed.');
    } finally {
      setSubmitting(false);
    }
  };
  const unlockForEdit = async () => {
    if (!campaign) return;
    const r = await unlockCampaign(campaign.id);
    setCampaign(r.data);
    toast.success('Unlocked — edit and re-lock when done.');
  };

  // ── step 3 events ────────────────────────────────────────────────
  const handleSearchEvents = async () => {
    setSearchingEvents(true);
    try {
      const res = await searchEvents({
        markets,
        date_range_start: dateRangeStart,
        date_range_end: dateRangeEnd,
        categories: ['festivals', 'holidays'],
      });
      setEventResults(res.data?.results || []);
    } catch (err) {
      toast.error('Event search failed.');
    } finally {
      setSearchingEvents(false);
    }
  };
  const toggleEvent = (event) => {
    setEvents((prev) => {
      const i = prev.findIndex((e) => e.title === event.title && e.date === event.date);
      if (i >= 0) return prev.filter((_, k) => k !== i);
      return [...prev, event];
    });
  };
  const skipEvents = async () => {
    if (campaign) {
      try { await patchCampaign(campaign.id, { events: [] }); } catch {}
    }
    setEvents([]);
    setStep(4);
  };
  const saveEventsAndContinue = async () => {
    if (campaign) {
      try { await patchCampaign(campaign.id, { events }); } catch {}
    }
    setStep(4);
  };

  // ── step 4 selection ─────────────────────────────────────────────
  const selectionValid = useMemo(() => {
    if (!pickerSel) return false;
    return ((pickerSel.hotel_ids?.length || 0)
      + (pickerSel.brand_ids?.length || 0)
      + (pickerSel.cities?.length || 0)) > 0;
  }, [pickerSel]);

  const toggleLevel = (id) => setLevelsSel((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  const toggleChannel = (id) => setChannelsSel((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);

  const continueToGenerate = async () => {
    if (!selectionValid) { toast.error('Pick at least one property, brand, or city.'); return; }
    if (channelsSel.length === 0) { toast.error('Pick at least one channel.'); return; }
    if (levelsSel.length === 0) { toast.error('Pick at least one campaign level.'); return; }

    const sel = {
      scope: pickerSel.scope || 'multi',
      hotel_id: pickerSel.hotel_ids?.[0] || '',
      brand_id: pickerSel.brand_ids?.[0] || '',
      hotel_ids: pickerSel.hotel_ids || [],
      brand_ids: pickerSel.brand_ids || [],
      cities: pickerSel.cities || [],
      is_loyalty: !!pickerSel.is_loyalty,
      campaign_levels: levelsSel,
      channels: channelsSel,
    };
    setSharedSelection(pickerSel);    // mirror to the shared context so Hub / other tools pre-fill
    try { await patchCampaign(campaign.id, { selection: sel }); } catch {}
    setStep(5);
  };

  // ── step 5 generate ──────────────────────────────────────────────
  const runGenerate = async () => {
    if (!campaign) return;
    setGenerating(true);
    setResults([]);
    try {
      const sel = {
        scope: pickerSel.scope || 'multi',
        hotel_id: pickerSel.hotel_ids?.[0] || '',
        brand_id: pickerSel.brand_ids?.[0] || '',
        hotel_ids: pickerSel.hotel_ids || [],
        brand_ids: pickerSel.brand_ids || [],
        cities: pickerSel.cities || [],
        is_loyalty: !!pickerSel.is_loyalty,
        campaign_levels: levelsSel,
        channels: channelsSel,
      };
      const r = await generateCampaign(campaign.id, { selection: sel });
      setResults(r.data?.results || []);
      toast.success(`Generated ${r.data?.results?.length || 0} group(s) · ${r.data?.total_tokens || 0} tokens.`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Campaign generation failed.');
    } finally {
      setGenerating(false);
    }
  };

  const downloadCsv = () => {
    const rows = [['campaign', 'entity', 'scope', 'channel', 'level', 'idx', 'headline', 'description']];
    const cname = structured.campaign_name || campaign?.structured?.campaign_name || 'campaign';
    for (const r of results || []) {
      const variants = r.variants || [];
      variants.forEach((v, i) => {
        const headlines = v.headlines || (v.headline ? [v.headline] : (v.title ? [v.title] : []));
        const descriptions = v.descriptions || (v.description ? [v.description] : (v.body ? [v.body] : []));
        const maxLen = Math.max(headlines.length, descriptions.length, 1);
        for (let k = 0; k < maxLen; k++) {
          rows.push([
            cname,
            r.label,
            r.scope,
            r.channel,
            r.level,
            `${i + 1}.${k + 1}`,
            (headlines[k] || '').replace(/"/g, '""'),
            (descriptions[k] || '').replace(/"/g, '""'),
          ]);
        }
      });
    }
    const csv = rows.map((r) => r.map((c) => `"${(c ?? '').toString().replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${cname.replace(/[^a-z0-9]+/gi, '_')}_unified.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ──────────────────────────────────────────────────────────────────
  return (
    <div className="em-scope" style={{ padding: '8px 4px 32px' }}>
      <div className="page-header">
        <h1>Unified <em style={{ color: 'var(--em-accent)' }}>Campaign</em></h1>
        {campaign && (
          <span className={`em-pill ${isLocked ? 'accent' : 'muted'}`} style={{ marginLeft: 12 }}>
            {isLocked ? <><Lock size={11} style={{ marginRight: 4, verticalAlign: '-1px' }} /> Locked</> : <><Unlock size={11} style={{ marginRight: 4, verticalAlign: '-1px' }} /> Draft</>}
          </span>
        )}
      </div>

      <div className="wizard-steps" style={{ marginTop: 12 }}>
        {STEPS.map((s) => (
          <div key={s.num} className={`wizard-step ${step === s.num ? 'active' : ''} ${step > s.num ? 'completed' : ''}`}>
            <div className="wizard-step-circle">{s.num}</div>
            <span className="wizard-step-label">{s.label}</span>
          </div>
        ))}
      </div>

      <div className="wizard-content">
        {/* STEP 1 — Brief */}
        {step === 1 && (
          <section className="wizard-panel">
            <h2>Tell us about the campaign</h2>
            <p style={{ color: 'var(--em-ink-soft)', fontSize: 13, marginTop: -4 }}>
              Write freely. The system will structure your input — include any of: campaign name,
              start / end dates, booking window, cancellation policy, participating hotels, promo code,
              landing page URL, inclusions, target audience.
            </p>
            <div className="form-group" style={{ marginTop: 12 }}>
              <label>Campaign brief *</label>
              <textarea
                rows={10}
                value={raw}
                onChange={(e) => setRaw(e.target.value)}
                placeholder="e.g. ITC Maratha Diwali 2026, 25% off + complimentary breakfast, valid 15 Oct–5 Nov, book by Oct 10, no cancellation after Oct 25, promo code DIWALI25, landing page itchotels.com/diwali, target millennials and family travellers..."
              />
            </div>
            <div className="form-group" style={{ position: 'relative' }}>
              <label>Reference URLs <span style={{ fontSize: '0.7rem', fontWeight: 400, textTransform: 'none' }}>(optional, type & Enter)</span></label>
              <div className="url-tags-container" onClick={() => document.getElementById('uc-url')?.focus()}>
                {refUrls.map((u, i) => (
                  <div key={i} className="url-tag">
                    <span>{u.replace(/^https?:\/\//, '').slice(0, 40)}</span>
                    <button type="button" onClick={() => setRefUrls((p) => p.filter((_, k) => k !== i))}><X size={12} /></button>
                  </div>
                ))}
                <input
                  id="uc-url"
                  className="url-tags-input"
                  value={refUrlInput}
                  onChange={(e) => setRefUrlInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      const v = refUrlInput.trim();
                      if (!v) return;
                      const url = v.startsWith('http') ? v : `https://${v}`;
                      if (!refUrls.includes(url)) setRefUrls([...refUrls, url]);
                      setRefUrlInput('');
                    }
                  }}
                  placeholder={refUrls.length === 0 ? 'hotel-website.com or paste full URL' : 'Add another URL…'}
                />
              </div>
            </div>
            <div className="wizard-nav">
              <div className="wizard-nav-spacer" />
              <button className="btn btn-primary" onClick={submitBrief} disabled={submitting || !raw.trim()}>
                {submitting ? 'Structuring…' : <>Structure brief <ChevronRight size={16} /></>}
              </button>
            </div>
          </section>
        )}

        {/* STEP 2 — Finalize */}
        {step === 2 && (
          <section className="wizard-panel">
            <h2>Finalize the brief</h2>
            <p style={{ color: 'var(--em-ink-soft)', fontSize: 13, marginTop: -4 }}>
              Review the structured fields, edit anything that's off, then lock the campaign. Locked briefs are immutable —
              you can always unlock from <strong>My Account → Unified Briefs</strong>.
            </p>
            <div className="form-row">
              <div className="form-group">
                <label>Campaign name *</label>
                <input value={structured.campaign_name} onChange={(e) => setStructured({ ...structured, campaign_name: e.target.value })} disabled={isLocked} />
              </div>
              <div className="form-group">
                <label>Promo code</label>
                <input value={structured.promo_code} onChange={(e) => setStructured({ ...structured, promo_code: e.target.value.toUpperCase() })} disabled={isLocked} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Start date</label>
                <input type="date" value={structured.start_date} onChange={(e) => setStructured({ ...structured, start_date: e.target.value })} disabled={isLocked} />
              </div>
              <div className="form-group">
                <label>End date</label>
                <input type="date" value={structured.end_date} onChange={(e) => setStructured({ ...structured, end_date: e.target.value })} disabled={isLocked} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Booking window start</label>
                <input type="date" value={structured.booking_window_start} onChange={(e) => setStructured({ ...structured, booking_window_start: e.target.value })} disabled={isLocked} />
              </div>
              <div className="form-group">
                <label>Booking window end</label>
                <input type="date" value={structured.booking_window_end} onChange={(e) => setStructured({ ...structured, booking_window_end: e.target.value })} disabled={isLocked} />
              </div>
            </div>
            <div className="form-group">
              <label>Inclusions</label>
              <input value={structured.inclusions} onChange={(e) => setStructured({ ...structured, inclusions: e.target.value })} disabled={isLocked} />
            </div>
            <div className="form-group">
              <label>Cancellation policy</label>
              <input value={structured.cancellation_policy} onChange={(e) => setStructured({ ...structured, cancellation_policy: e.target.value })} disabled={isLocked} />
            </div>
            <div className="form-group">
              <label>Landing page URL</label>
              <input value={structured.landing_page_url} onChange={(e) => setStructured({ ...structured, landing_page_url: e.target.value })} disabled={isLocked} />
            </div>
            <div className="form-group">
              <label>Target audience</label>
              <input value={structured.target_audience} onChange={(e) => setStructured({ ...structured, target_audience: e.target.value })} disabled={isLocked} />
            </div>
            <div className="form-group">
              <label>Summary</label>
              <textarea rows={3} value={structured.summary} onChange={(e) => setStructured({ ...structured, summary: e.target.value })} disabled={isLocked} />
            </div>

            <div className="wizard-nav">
              <button className="btn btn-outline" onClick={() => setStep(1)}>
                <ChevronLeft size={16} /> Back
              </button>
              <div className="wizard-nav-spacer" />
              {!isLocked && (
                <>
                  <button className="btn btn-outline" onClick={saveStructured} style={{ marginRight: 8 }}>
                    Save draft
                  </button>
                  <button className="btn btn-primary" onClick={lockAndContinue} disabled={submitting}>
                    <Lock size={14} /> {submitting ? 'Locking…' : 'Lock & continue'}
                  </button>
                </>
              )}
              {isLocked && (
                <>
                  <button className="btn btn-outline" onClick={unlockForEdit} style={{ marginRight: 8 }}>
                    <Unlock size={14} /> Unlock to edit
                  </button>
                  <button className="btn btn-primary" onClick={() => setStep(3)}>
                    Continue <ChevronRight size={16} />
                  </button>
                </>
              )}
            </div>
          </section>
        )}

        {/* STEP 3 — Events */}
        {step === 3 && (
          <section className="wizard-panel">
            <h2>Events <span style={{ fontSize: '0.8rem', fontWeight: 400 }}>(optional)</span></h2>
            <div className="form-row">
              <div className="form-group">
                <label>Date range start</label>
                <input type="date" value={dateRangeStart} onChange={(e) => setDateRangeStart(e.target.value)} />
              </div>
              <div className="form-group">
                <label>Date range end</label>
                <input type="date" value={dateRangeEnd} onChange={(e) => setDateRangeEnd(e.target.value)} />
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <button className="btn btn-primary" onClick={handleSearchEvents} disabled={searchingEvents}>
                <Search size={16} /> {searchingEvents ? 'Searching…' : 'Search Events'}
              </button>
              <button type="button" className="btn btn-outline" onClick={skipEvents}>
                Skip events <ChevronRight size={14} />
              </button>
              <span style={{ fontSize: 12, color: 'var(--em-ink-soft)' }}>
                Events are optional — skip to continue.
              </span>
            </div>
            {eventResults.length > 0 && (
              <>
                <h4 style={{ marginTop: '1rem' }}>Found {eventResults.length} events</h4>
                <EventCalendar events={eventResults} selectedEvents={events} onToggleEvent={toggleEvent} />
              </>
            )}
            <div className="wizard-nav">
              <button className="btn btn-outline" onClick={() => setStep(2)}>
                <ChevronLeft size={16} /> Back
              </button>
              <div className="wizard-nav-spacer" />
              <button className="btn btn-primary" onClick={saveEventsAndContinue}>
                Next <ChevronRight size={16} />
              </button>
            </div>
          </section>
        )}

        {/* STEP 4 — Properties + Channels + Levels */}
        {step === 4 && (
          <section className="wizard-panel">
            <h2>Properties, channels & levels</h2>
            <div className="form-group">
              <label>Property / Brand / City *</label>
              <IntelligentPropertyPicker
                value={pickerSel}
                onChange={setPickerSel}
                scopeSummary={null}
              />
            </div>

            <div className="form-group">
              <label>Campaign levels *</label>
              <div className="checkbox-grid">
                {LEVELS.map((l) => (
                  <label key={l.id} className="checkbox-label">
                    <input type="checkbox" checked={levelsSel.includes(l.id)} onChange={() => toggleLevel(l.id)} />
                    {l.label}
                  </label>
                ))}
              </div>
              <p style={{ fontSize: 12, color: 'var(--em-ink-soft)', marginTop: 4 }}>
                Chain = one ad written at the brand level. Single = one ad per property. Chain + per-property = both.
              </p>
            </div>

            <div className="form-group">
              <label>Channels *</label>
              <div className="checkbox-grid">
                {CHANNELS.map((c) => (
                  <label key={c.id} className="checkbox-label">
                    <input type="checkbox" checked={channelsSel.includes(c.id)} onChange={() => toggleChannel(c.id)} />
                    {c.label}
                  </label>
                ))}
              </div>
            </div>

            <div className="wizard-nav">
              <button className="btn btn-outline" onClick={() => setStep(3)}>
                <ChevronLeft size={16} /> Back
              </button>
              <div className="wizard-nav-spacer" />
              <button className="btn btn-primary" onClick={continueToGenerate} disabled={!selectionValid || levelsSel.length === 0 || channelsSel.length === 0}>
                Continue to generate <ChevronRight size={16} />
              </button>
            </div>
          </section>
        )}

        {/* STEP 5 — Generate */}
        {step === 5 && (
          <section className="wizard-panel">
            <h2>Generate the campaign</h2>
            {!results.length && !generating && (
              <>
                <p style={{ color: 'var(--em-ink-soft)', fontSize: 13 }}>
                  Click Generate. The orchestrator scrapes your reference URLs, fetches reviews, pulls past learning, and
                  produces ad copies for every selected entity × channel × level (variants honour each channel's character limits).
                </p>
                <button className="btn btn-primary btn-generate" onClick={runGenerate}>
                  <Zap size={16} /> Generate campaign
                </button>
              </>
            )}
            {generating && <GenerationProgress />}
            {!generating && results.length > 0 && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <h3 style={{ margin: 0 }}>{results.length} generation{results.length !== 1 ? 's' : ''}</h3>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-outline" onClick={runGenerate}>
                      <Sparkles size={14} /> Regenerate all
                    </button>
                    <button className="btn btn-primary" onClick={downloadCsv}>
                      <Download size={14} /> Export CSV
                    </button>
                  </div>
                </div>

                {results.map((r, idx) => (
                  <div key={idx} className="em-card" style={{ marginBottom: 12 }}>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'baseline', flexWrap: 'wrap' }}>
                      <strong>{r.label}</strong>
                      <span className="em-pill">{r.channel}</span>
                      <span className="em-pill muted">{r.level}</span>
                      <span style={{ fontSize: 11, color: 'var(--em-ink-faint)', marginLeft: 'auto' }}>
                        {r.tokens_used} tokens · {r.time_seconds}s · {r.model_used}
                      </span>
                    </div>
                    {r.error ? (
                      <p style={{ fontSize: 12, color: 'var(--em-accent)', marginTop: 8 }}>{r.error}</p>
                    ) : (
                      <div style={{ marginTop: 10, display: 'grid', gap: 8 }}>
                        {(r.variants || []).map((v, vi) => (
                          <VariantBlock
                            key={vi}
                            variant={v}
                            onEdit={(updated) => {
                              const next = [...results];
                              next[idx] = { ...r, variants: r.variants.map((x, j) => j === vi ? updated : x) };
                              setResults(next);
                            }}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </>
            )}

            <div className="wizard-nav" style={{ marginTop: 16 }}>
              <button className="btn btn-outline" onClick={() => setStep(4)}>
                <ChevronLeft size={16} /> Back
              </button>
              <div className="wizard-nav-spacer" />
              <button className="btn btn-outline" onClick={() => navigate('/account')}>
                Done — view in My Account
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function VariantBlock({ variant, onEdit }) {
  const [editing, setEditing] = useState(false);
  const [v, setV] = useState(variant);

  const headlines = v.headlines || (v.headline ? [v.headline] : []);
  const descriptions = v.descriptions || (v.description ? [v.description] : []);
  const body = v.body || '';

  return (
    <div style={{ padding: 10, borderRadius: 8, border: '1px solid var(--em-line)', background: 'var(--em-surface-2)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
        <span style={{ fontSize: 11, color: 'var(--em-ink-faint)' }}>{v.platform || ''}</span>
        <button type="button" className="btn btn-sm btn-outline" onClick={() => {
          if (editing) onEdit?.(v);
          setEditing(!editing);
        }}>
          {editing ? 'Save' : 'Edit'}
        </button>
      </div>
      {headlines.length > 0 && (
        <div style={{ display: 'grid', gap: 4 }}>
          {headlines.map((h, i) => (
            <div key={`h-${i}`} style={{ fontWeight: 600, fontSize: 13 }}>
              {editing ? (
                <input
                  value={h}
                  onChange={(e) => {
                    const arr = [...headlines]; arr[i] = e.target.value;
                    setV({ ...v, headlines: arr });
                  }}
                  style={{ width: '100%' }}
                />
              ) : h}
            </div>
          ))}
        </div>
      )}
      {descriptions.length > 0 && (
        <div style={{ display: 'grid', gap: 4, marginTop: 6 }}>
          {descriptions.map((d, i) => (
            <div key={`d-${i}`} style={{ fontSize: 12, color: 'var(--em-ink-soft)' }}>
              {editing ? (
                <textarea
                  value={d}
                  onChange={(e) => {
                    const arr = [...descriptions]; arr[i] = e.target.value;
                    setV({ ...v, descriptions: arr });
                  }}
                  rows={2}
                  style={{ width: '100%' }}
                />
              ) : d}
            </div>
          ))}
        </div>
      )}
      {body && (
        <div style={{ marginTop: 6, fontSize: 12 }}>
          {editing ? (
            <textarea value={body} onChange={(e) => setV({ ...v, body: e.target.value })} rows={3} style={{ width: '100%' }} />
          ) : body}
        </div>
      )}
    </div>
  );
}
