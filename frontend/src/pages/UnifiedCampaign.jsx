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
  Zap, ChevronLeft, ChevronRight, Lock, Unlock, Search, X, Download, Sparkles, Plus, ArrowRight,
} from 'lucide-react';
import {
  createCampaign, getCampaign, patchCampaign, lockCampaign, unlockCampaign,
  generateCampaign, searchEvents, listPastBriefs, listIdeations,
  // v3.0 streaming
  generateCampaignAsync, getCampaignJob, getCampaignGenerations,
  steerCampaign, cancelCampaign, regenStaleCampaign, resumeCampaign,
} from '../services/api';
import IntelligentPropertyPicker from '../components/IntelligentPropertyPicker';
import EventCalendar from '../components/EventCalendar';
import GenerationProgress from '../components/GenerationProgress';
import { useSelection } from '../contexts/SelectionContext';

function formatDate(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
  } catch { return ''; }
}

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

  // v2.9 — landing view state (only used when no ?campaign= in URL).
  const [showLanding, setShowLanding] = useState(false);
  const [pastBriefs, setPastBriefs] = useState([]);
  const [ideatedCampaigns, setIdeatedCampaigns] = useState([]);
  const [loadingLanding, setLoadingLanding] = useState(false);

  // v3.0 — streaming fan-out state
  const [streamMode, setStreamMode] = useState(false);
  const [jobState, setJobState] = useState(null);           // {job_id, total_tasks, ..., last_heartbeat}
  const [streamRows, setStreamRows] = useState(new Map());  // idx -> GenerationRow
  const [streamSince, setStreamSince] = useState(-1);
  const [steerOpen, setSteerOpen] = useState(false);
  const [steerStructured, setSteerStructured] = useState(null);
  const [steerScope, setSteerScope] = useState('remaining');

  const isLocked = campaign?.status === 'locked';
  // v2.9 — when the campaign was promoted from an Ideation, skip the Brief step.
  const fromIdeation = !!campaign?.ideation_id;
  const visibleSteps = useMemo(() => (
    fromIdeation ? STEPS.filter((s) => s.num !== 1) : STEPS
  ), [fromIdeation]);

  // v2.9 — load the landing view when the user opens /unified with no query.
  useEffect(() => {
    if (queryId) { setShowLanding(false); return; }
    setShowLanding(true);
    setLoadingLanding(true);
    (async () => {
      try {
        const [pb, idc] = await Promise.all([
          listPastBriefs(5).catch(() => ({ data: [] })),
          listIdeations(20, { status: 'in_progress' }).catch(() => ({ data: [] })),
        ]);
        setPastBriefs(pb.data || []);
        setIdeatedCampaigns(idc.data || []);
      } finally {
        setLoadingLanding(false);
      }
    })();
  }, [queryId]);

  const startNewCampaign = () => { setShowLanding(false); setStep(1); };
  const openPastBrief = (id) => navigate(`/unified?campaign=${encodeURIComponent(id)}`);
  const resumeIdeation = (id) => navigate(`/ideation?id=${encodeURIComponent(id)}`);

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
  // v3.0 — Auto-pick streaming when the fan-out is large.
  // entity count = hotel_ids + brand_ids + cities; total tasks roughly
  // = entities * channels * levels (chain_plus_single doubles).
  const entityCount = useMemo(() => (
    (pickerSel?.hotel_ids?.length || 0)
    + (pickerSel?.brand_ids?.length || 0)
    + (pickerSel?.cities?.length || 0)
  ), [pickerSel]);
  const expectedTasks = useMemo(() => {
    const lvl = (levelsSel || []).reduce((a, l) => a + (l === 'chain_plus_single' ? 2 : 1), 0) || 1;
    const ch = (channelsSel || []).length || 1;
    return Math.max(entityCount * ch * lvl, 1);
  }, [entityCount, levelsSel, channelsSel]);
  const useStream = expectedTasks > 5;

  const runGenerate = async () => {
    if (!campaign) return;
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

    if (useStream) {
      // Streaming path — POST returns in <1s, polling drives the UI.
      setGenerating(true);
      setResults([]);
      setStreamRows(new Map());
      setStreamSince(-1);
      try {
        const r = await generateCampaignAsync(campaign.id, sel);
        setJobState({
          job_id: r.data?.job_id,
          total_tasks: r.data?.total_tasks,
          brief_revision: r.data?.brief_revision || 0,
          completed_tasks: 0, failed_tasks: 0, stale_tasks: 0,
          cancelled: false,
          last_heartbeat: new Date().toISOString(),
        });
        setStreamMode(true);
        toast.success(`Generating ${r.data?.total_tasks || 0} ad copies — streaming in.`);
      } catch (err) {
        toast.error(err.response?.data?.detail || 'Could not start streaming generation.');
        setGenerating(false);
      }
      return;
    }

    // Legacy sync path for small fan-outs (1-5 tasks).
    setGenerating(true);
    setResults([]);
    try {
      const r = await generateCampaign(campaign.id, { selection: sel });
      setResults(r.data?.results || []);
      toast.success(`Generated ${r.data?.results?.length || 0} group(s) · ${r.data?.total_tokens || 0} tokens.`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Campaign generation failed.');
    } finally {
      setGenerating(false);
    }
  };

  // v3.0 — Streaming polling loop. Runs while streamMode=true.
  // Polls /generations every 2s and merges into streamRows Map.
  useEffect(() => {
    if (!streamMode || !campaign?.id) return undefined;
    let cancelled = false;
    let timer = null;

    const tick = async () => {
      if (cancelled) return;
      try {
        const [jobResp, gensResp] = await Promise.all([
          getCampaignJob(campaign.id),
          getCampaignGenerations(campaign.id, streamSince, 200),
        ]);
        if (cancelled) return;
        const job = jobResp.data?.job;
        if (job) setJobState(job);
        const newRows = gensResp.data?.rows || [];
        if (newRows.length > 0) {
          setStreamRows((prev) => {
            const next = new Map(prev);
            newRows.forEach((row) => next.set(row.idx, row));
            return next;
          });
          const maxIdx = newRows.reduce((m, r) => Math.max(m, r.idx), streamSince);
          setStreamSince(maxIdx);
        }
        // Stop polling when terminal.
        const total = job?.total_tasks || 0;
        const done = (job?.completed_tasks || 0) + (job?.failed_tasks || 0);
        const stale = job?.stale_tasks || 0;
        if (total > 0 && (done + stale) >= total) {
          setGenerating(false);
          // Mirror into the legacy results array for the existing CSV download path.
          const arr = Array.from(new Map(streamRows).values())
            .filter((r) => r.status === 'complete')
            .sort((a, b) => a.idx - b.idx);
          if (arr.length > 0) setResults(arr);
          if (!cancelled) timer = setTimeout(tick, 5000);   // slower idle poll
          return;
        }
      } catch (err) {
        // Tolerate transient errors, keep polling.
      }
      if (!cancelled) timer = setTimeout(tick, 2000);
    };
    tick();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamMode, campaign?.id]);

  // Hydrate streaming view when the campaign comes back as status='generating'.
  useEffect(() => {
    if (campaign?.status === 'generating' && !streamMode) {
      setStreamMode(true);
      setStreamSince(-1);
      setStreamRows(new Map());
      setGenerating(true);
    }
  }, [campaign?.status, streamMode]);

  // Streaming-mode helpers
  const onSteerSubmit = async () => {
    if (!campaign?.id || !steerStructured) return;
    try {
      const r = await steerCampaign(campaign.id, steerStructured, steerScope);
      toast.success(`Brief revision ${r.data?.brief_revision}. ${steerScope === 'all' ? `${r.data?.completed_marked_stale} completed cards flipped to stale.` : 'Remaining tasks will use the new brief.'}`);
      setSteerOpen(false);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Steer failed.');
    }
  };
  const onCancelJob = async () => {
    if (!campaign?.id) return;
    if (!window.confirm('Cancel this job? Pending tasks will stop. You can resume later.')) return;
    try {
      await cancelCampaign(campaign.id);
      toast.success('Cancelling — in-flight tasks will finish, queued ones will stop.');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Cancel failed.');
    }
  };
  const onRegenStale = async () => {
    if (!campaign?.id) return;
    try {
      const r = await regenStaleCampaign(campaign.id);
      toast.success(`${r.data?.flipped} stale rows queued for regeneration.`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Regen-stale failed.');
    }
  };
  const onResumeJob = async () => {
    if (!campaign?.id) return;
    try {
      await resumeCampaign(campaign.id);
      toast.success('Resumed.');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Resume failed.');
    }
  };

  // Heartbeat-stale detection (>60s old)
  const heartbeatStale = useMemo(() => {
    if (!jobState?.last_heartbeat) return false;
    const total = jobState.total_tasks || 0;
    const done = (jobState.completed_tasks || 0) + (jobState.failed_tasks || 0);
    if (total > 0 && done >= total) return false;
    const last = new Date(jobState.last_heartbeat).getTime();
    return (Date.now() - last) > 60_000;
  }, [jobState]);

  const streamArray = useMemo(() => Array.from(streamRows.values()).sort((a, b) => a.idx - b.idx), [streamRows]);
  const counts = useMemo(() => {
    const c = { pending: 0, running: 0, complete: 0, failed: 0, stale: 0 };
    streamArray.forEach((r) => { c[r.status] = (c[r.status] || 0) + 1; });
    return c;
  }, [streamArray]);

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
        <h1>Unified <em style={{ color: 'var(--em-accent)' }}>Campaign Copy</em></h1>
        {campaign?.campaign_id && (
          <span className="id-chip" style={{ marginLeft: 12 }} title="Campaign ID">#{campaign.campaign_id}</span>
        )}
        {campaign && (
          <span className={`em-pill ${isLocked ? 'accent' : 'muted'}`} style={{ marginLeft: 12 }}>
            {isLocked ? <><Lock size={11} style={{ marginRight: 4, verticalAlign: '-1px' }} /> Locked</> : <><Unlock size={11} style={{ marginRight: 4, verticalAlign: '-1px' }} /> Draft</>}
          </span>
        )}
      </div>

      {showLanding && (
        <section style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button className="btn btn-primary" onClick={startNewCampaign}>
              <Plus size={16} /> New campaign
            </button>
          </div>

          <section>
            <h3 className="em-display" style={{ marginBottom: 8 }}>Past briefs</h3>
            <p style={{ color: 'var(--em-ink-soft)', marginTop: 0, fontSize: 13 }}>
              Your last five locked campaigns. Open one to review or generate again.
            </p>
            {loadingLanding && <p className="muted">Loading…</p>}
            {!loadingLanding && pastBriefs.length === 0 && (
              <p className="muted">No locked campaigns yet — finalise a brief to see it here.</p>
            )}
            {pastBriefs.map((b) => (
              <button
                key={b.id}
                className="past-brief-row"
                onClick={() => openPastBrief(b.id)}
                type="button"
              >
                <span className="id-chip">#{b.campaign_id || '·····'}</span>
                <span className="row-title">{b.campaign_name || 'Untitled brief'}</span>
                <span className="em-pill accent">{b.status}</span>
                <span className="row-date">{formatDate(b.locked_at || b.updated_at || b.created_at)}</span>
                <ArrowRight size={14} className="row-arrow" />
              </button>
            ))}
          </section>

          <section>
            <h3 className="em-display" style={{ marginBottom: 8 }}>Ideated campaigns</h3>
            <p style={{ color: 'var(--em-ink-soft)', marginTop: 0, fontSize: 13 }}>
              Brainstorming sessions in progress. Resume any time — every iteration is preserved.
            </p>
            {loadingLanding && <p className="muted">Loading…</p>}
            {!loadingLanding && ideatedCampaigns.length === 0 && (
              <p className="muted">No in-progress ideations yet — start one from Campaign Ideation.</p>
            )}
            {ideatedCampaigns.map((it) => {
              const offer = it.inputs?.offer_name || it.theme_text || 'Untitled idea';
              const phase = it.phase || 'inputs';
              const hr = it.inputs?.hotels_resolution || {};
              const hotelCount = (hr.resolved_hotel_ids || []).length;
              return (
                <button
                  key={it.id}
                  className="past-brief-row"
                  onClick={() => resumeIdeation(it.id)}
                  type="button"
                >
                  <span className="id-chip">#{it.campaign_id || '·····'}</span>
                  <span className="row-title">{offer}</span>
                  <span className="em-pill muted">{phase}</span>
                  <span className="row-date">
                    {hotelCount > 0 ? `${hotelCount} hotels · ` : ''}
                    {formatDate(it.updated_at || it.created_at)}
                  </span>
                  <ArrowRight size={14} className="row-arrow" />
                </button>
              );
            })}
          </section>
        </section>
      )}

      {!showLanding && (
      <>
      <div className="wizard-steps" style={{ marginTop: 12 }}>
        {visibleSteps.map((s) => (
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
            {!results.length && !generating && !streamMode && (
              <>
                <p style={{ color: 'var(--em-ink-soft)', fontSize: 13 }}>
                  Click Generate. The orchestrator scrapes your reference URLs, fetches reviews, pulls past learning, and
                  produces ad copies for every selected entity × channel × level (variants honour each channel's character limits).
                  {useStream && (
                    <span style={{ display: 'block', marginTop: 6, fontStyle: 'italic' }}>
                      <strong>{expectedTasks}</strong> ad copies expected — streaming as they're ready. You can steer the brief mid-flight.
                    </span>
                  )}
                </p>
                <button className="btn btn-primary btn-generate" onClick={runGenerate}>
                  <Zap size={16} /> Generate campaign
                </button>
              </>
            )}

            {/* v3.0 — Streaming view */}
            {streamMode && (
              <div className="streaming-view">
                <div className="streaming-header em-card" style={{ padding: 14, marginBottom: 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                    <div>
                      <strong>
                        {counts.complete + counts.failed} / {jobState?.total_tasks || streamArray.length || expectedTasks} complete
                      </strong>
                      <span style={{ color: 'var(--em-ink-soft)', marginLeft: 12, fontSize: 13 }}>
                        running {counts.running} · pending {counts.pending} · failed {counts.failed}
                        {counts.stale > 0 && ` · stale ${counts.stale}`}
                      </span>
                      {jobState && (
                        <span style={{ color: 'var(--em-ink-soft)', marginLeft: 12, fontSize: 12, fontFamily: 'var(--em-mono, monospace)' }}>
                          rev {jobState.brief_revision || 0}
                        </span>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button className="btn btn-outline btn-sm" onClick={() => {
                        setSteerStructured({ ...structured });
                        setSteerScope('remaining');
                        setSteerOpen(true);
                      }}>
                        <Sparkles size={14} /> Steer the brief
                      </button>
                      {counts.stale > 0 && (
                        <button className="btn btn-outline btn-sm" onClick={onRegenStale}>
                          <Sparkles size={14} /> Regen {counts.stale} stale
                        </button>
                      )}
                      <button className="btn btn-outline btn-sm" onClick={onCancelJob}>
                        <X size={14} /> Cancel
                      </button>
                    </div>
                  </div>
                  <div className="stream-progress-bar" style={{ marginTop: 10 }}>
                    <div
                      className="stream-progress-fill"
                      style={{
                        width: `${jobState?.total_tasks ? Math.round(100 * (counts.complete + counts.failed) / jobState.total_tasks) : 0}%`,
                      }}
                    />
                  </div>
                  {heartbeatStale && (
                    <div className="stream-stalled-banner">
                      Worker appears stalled — last heartbeat over 60 s ago.
                      <button className="btn btn-outline btn-sm" onClick={onResumeJob} style={{ marginLeft: 12 }}>Resume</button>
                    </div>
                  )}
                </div>

                <div className="streaming-grid">
                  {streamArray.map((row) => (
                    <article key={row.idx} className={`stream-row stream-row-${row.status}`}>
                      <div className="stream-row-head">
                        <span className="stream-idx">#{row.idx + 1}</span>
                        <strong className="stream-label">{row.label || `Task ${row.idx + 1}`}</strong>
                        <span className="em-pill muted">{row.channel}</span>
                        <span className="em-pill muted">{row.level}</span>
                        <span className={`stream-status stream-status-${row.status}`}>{row.status}</span>
                      </div>
                      {row.status === 'complete' && Array.isArray(row.variants) && row.variants.length > 0 && (
                        <div className="stream-row-body">
                          {row.variants.slice(0, 1).map((v, i) => (
                            <VariantBlock key={i} variant={v} />
                          ))}
                          {row.variants.length > 1 && (
                            <p style={{ color: 'var(--em-ink-soft)', fontSize: 12, margin: '6px 0 0' }}>
                              + {row.variants.length - 1} more variant{row.variants.length > 2 ? 's' : ''} in the export
                            </p>
                          )}
                        </div>
                      )}
                      {row.status === 'failed' && (
                        <div className="stream-row-error">{row.error || 'Failed'}</div>
                      )}
                      {row.status === 'stale' && (
                        <div style={{ color: 'var(--em-ink-soft)', fontSize: 12, fontStyle: 'italic' }}>
                          Brief changed since this card was generated. Click "Regen stale" above to refresh.
                        </div>
                      )}
                      {(row.status === 'pending' || row.status === 'running') && (
                        <div className="stream-row-skeleton">
                          <div className="skel-line" />
                          <div className="skel-line skel-line-short" />
                        </div>
                      )}
                    </article>
                  ))}
                  {/* Placeholders for tasks the server hasn't surfaced yet */}
                  {jobState?.total_tasks > streamArray.length && (
                    Array.from({ length: jobState.total_tasks - streamArray.length }).slice(0, 50).map((_, i) => (
                      <article key={`ph-${i}`} className="stream-row stream-row-pending">
                        <div className="stream-row-head">
                          <span className="stream-idx">#{streamArray.length + i + 1}</span>
                          <span style={{ color: 'var(--em-ink-soft)' }}>queued</span>
                          <span className="stream-status stream-status-pending">pending</span>
                        </div>
                        <div className="stream-row-skeleton">
                          <div className="skel-line" />
                          <div className="skel-line skel-line-short" />
                        </div>
                      </article>
                    ))
                  )}
                </div>

                {(counts.complete + counts.failed + counts.stale) >= (jobState?.total_tasks || 0) && jobState?.total_tasks > 0 && (
                  <div style={{ marginTop: 16, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                    <button className="btn btn-primary" onClick={downloadCsv}>
                      <Download size={14} /> Export CSV
                    </button>
                  </div>
                )}
              </div>
            )}

            {generating && !streamMode && <GenerationProgress />}
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
      </>
      )}

      {/* v3.0 — Steer-brief modal */}
      {steerOpen && steerStructured && (
        <div className="modal-backdrop" onClick={(e) => { if (e.target.classList.contains('modal-backdrop')) setSteerOpen(false); }}>
          <div className="modal-shell">
            <header className="modal-head">
              <h3 style={{ margin: 0 }}>Steer the brief</h3>
              <button className="modal-x" onClick={() => setSteerOpen(false)}><X size={16} /></button>
            </header>
            <div className="modal-body">
              <p style={{ color: 'var(--em-ink-soft)', fontSize: 13, marginTop: 0 }}>
                Edit the structured brief. <strong>Remaining tasks</strong> will be generated with the new brief;
                <strong> already-completed</strong> ones can be flipped to stale (one-click regen).
              </p>
              <div className="form-row">
                <div className="form-group" style={{ flex: 1 }}>
                  <label>Campaign name</label>
                  <input type="text" value={steerStructured.campaign_name || ''} onChange={(e) => setSteerStructured({ ...steerStructured, campaign_name: e.target.value })} />
                </div>
              </div>
              <div className="form-group">
                <label>Inclusions</label>
                <textarea rows={2} value={steerStructured.inclusions || ''} onChange={(e) => setSteerStructured({ ...steerStructured, inclusions: e.target.value })} />
              </div>
              <div className="form-group">
                <label>Target audience</label>
                <input type="text" value={steerStructured.target_audience || ''} onChange={(e) => setSteerStructured({ ...steerStructured, target_audience: e.target.value })} />
              </div>
              <div className="form-group">
                <label>Summary / tone</label>
                <textarea rows={3} value={steerStructured.summary || ''} onChange={(e) => setSteerStructured({ ...steerStructured, summary: e.target.value })} />
              </div>
              <div className="form-group">
                <label>Apply steer to</label>
                <div className="hotels-tabs">
                  <button type="button" className={`tab-btn ${steerScope === 'remaining' ? 'active' : ''}`} onClick={() => setSteerScope('remaining')}>
                    Remaining tasks only
                  </button>
                  <button type="button" className={`tab-btn ${steerScope === 'all' ? 'active' : ''}`} onClick={() => setSteerScope('all')}>
                    All — flip completed to stale
                  </button>
                </div>
              </div>
            </div>
            <footer className="modal-foot">
              <button className="btn btn-outline" onClick={() => setSteerOpen(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={onSteerSubmit}>
                <Sparkles size={14} /> Apply steer
              </button>
            </footer>
          </div>
        </div>
      )}
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
