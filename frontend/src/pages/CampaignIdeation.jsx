/**
 * CampaignIdeation — upstream tool that produces a 10-concept shortlist
 * from a free-text theme + LLM critique chat. Phase 1 (v2.7).
 *
 * Flow: Setup (theme + dates + scope) → Critique (Q/A) → Shortlist (10 cards)
 *        → Done (redirect to /unified with new draft campaign).
 *
 * Honors the shared SelectionContext; the picker is the canonical
 * IntelligentPropertyPicker. Never accepts free-text property names.
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Sparkles, ChevronLeft, ChevronRight, Loader2, MessageCircle, CheckCircle2 } from 'lucide-react';
import IntelligentPropertyPicker from '../components/IntelligentPropertyPicker';
import { useSelection } from '../contexts/SelectionContext';
import { useAuth } from '../hooks/useAuth';
import {
  startIdeation,
  answerIdeation,
  generateShortlist,
  chooseShortlist,
} from '../services/api';

const STEPS = [
  { id: 1, label: 'Setup' },
  { id: 2, label: 'Critique' },
  { id: 3, label: 'Shortlist' },
  { id: 4, label: 'Done' },
];

function selectionFromPicker(p) {
  if (!p) return null;
  const hotel_ids = p.hotel_ids || [];
  const brand_ids = p.brand_ids || [];
  const cities = p.cities || [];
  const is_loyalty = !!p.is_loyalty;
  let scope = p.scope || 'hotel';
  let hotel_id = '';
  let brand_id = '';
  if (scope === 'hotel' && hotel_ids.length === 1) hotel_id = hotel_ids[0];
  if ((scope === 'brand' || scope === 'loyalty') && brand_ids.length === 1) brand_id = brand_ids[0];
  return {
    scope,
    hotel_id,
    brand_id,
    hotel_ids,
    brand_ids,
    cities,
    is_loyalty,
    generation_mode: null,
  };
}

function describeSelection(p) {
  if (!p) return '—';
  const labels = p._labels || {};
  const parts = [];
  if (p.is_loyalty) parts.push('Club ITC (Loyalty)');
  if (labels.brands?.length) parts.push(`${labels.brands.length} brand${labels.brands.length > 1 ? 's' : ''}`);
  if (labels.hotels?.length) parts.push(`${labels.hotels.length} hotel${labels.hotels.length > 1 ? 's' : ''}`);
  if (labels.cities?.length) parts.push(`${labels.cities.length} cit${labels.cities.length > 1 ? 'ies' : 'y'}`);
  return parts.length ? parts.join(' · ') : '—';
}

export default function CampaignIdeation() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { selection: sharedSelection, setSelection: setSharedSelection } = useSelection();

  const [step, setStep] = useState(1);

  // Setup state
  const [themeText, setThemeText] = useState('');
  const [dateStart, setDateStart] = useState('');
  const [dateEnd, setDateEnd] = useState('');
  const [pickerSel, setPickerSel] = useState(sharedSelection || null);

  useEffect(() => {
    if (!pickerSel && sharedSelection) setPickerSel(sharedSelection);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sharedSelection]);

  // Server state
  const [ideationId, setIdeationId] = useState('');
  const [history, setHistory] = useState([]); // [{q, a}]
  const [pendingQuestion, setPendingQuestion] = useState('');
  const [answerText, setAnswerText] = useState('');
  const [captured, setCaptured] = useState({});
  const [readyForShortlist, setReadyForShortlist] = useState(false);

  // Shortlist state
  const [shortlist, setShortlist] = useState([]);
  const [chosenIndex, setChosenIndex] = useState(null);

  const [loading, setLoading] = useState(false);

  const scopeSummary = user?.scope_summary || null;
  const setupValid = themeText.trim().length >= 6 && !!selectionFromPicker(pickerSel);

  const onStart = async () => {
    if (!setupValid) {
      toast.error('Add a theme and pick a property/brand to continue.');
      return;
    }
    setLoading(true);
    try {
      const sel = selectionFromPicker(pickerSel);
      setSharedSelection(pickerSel);
      const r = await startIdeation({
        theme_text: themeText.trim(),
        date_start: dateStart || '',
        date_end: dateEnd || '',
        selection: sel,
      });
      const data = r.data || {};
      setIdeationId(data.ideation_id);
      setPendingQuestion(data.next_question || '');
      setReadyForShortlist(!!data.ready_for_shortlist);
      setHistory([]);
      setStep(2);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not start ideation.');
    } finally {
      setLoading(false);
    }
  };

  const onAnswer = async () => {
    if (!answerText.trim() || !ideationId) return;
    setLoading(true);
    try {
      const ans = answerText.trim();
      const r = await answerIdeation(ideationId, ans);
      const data = r.data || {};
      setHistory((prev) => [...prev, { q: pendingQuestion, a: ans }]);
      setCaptured(data.captured || {});
      setAnswerText('');
      if (data.ready_for_shortlist) {
        setReadyForShortlist(true);
        setPendingQuestion('');
      } else {
        setPendingQuestion(data.next_question || '');
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not record answer.');
    } finally {
      setLoading(false);
    }
  };

  const onGenerateShortlist = async () => {
    if (!ideationId) return;
    setLoading(true);
    try {
      const r = await generateShortlist(ideationId);
      const items = r.data?.shortlist || [];
      setShortlist(items);
      setStep(3);
      if (!items.length) toast.error('Shortlist came back empty — try again.');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Shortlist generation failed.');
    } finally {
      setLoading(false);
    }
  };

  const onChoose = async (idx) => {
    if (!ideationId) return;
    setLoading(true);
    try {
      const r = await chooseShortlist(ideationId, idx);
      setChosenIndex(idx);
      const ucid = r.data?.unified_campaign_id;
      setStep(4);
      if (ucid) {
        setTimeout(() => navigate(`/unified?campaign_id=${ucid}`), 1200);
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not promote concept.');
    } finally {
      setLoading(false);
    }
  };

  const stepIndicator = useMemo(() => (
    <div className="wizard-steps">
      {STEPS.map((s) => (
        <div key={s.id} className={`wizard-step ${step === s.id ? 'active' : ''} ${step > s.id ? 'done' : ''}`}>
          <div className="wizard-step-num">{s.id}</div>
          <div className="wizard-step-label">{s.label}</div>
        </div>
      ))}
    </div>
  ), [step]);

  return (
    <div className="page-shell">
      <header className="page-header">
        <div className="page-title-row">
          <Sparkles size={20} />
          <h1>Campaign Ideation</h1>
        </div>
        <p className="page-subtitle">
          Describe the theme, answer a short critique, and pick from 10 shortlisted concepts.
        </p>
      </header>

      {stepIndicator}

      {step === 1 && (
        <section className="wizard-panel">
          <h2>Setup</h2>
          <div className="form-group">
            <label>Theme / event / mood *</label>
            <textarea
              rows={3}
              placeholder='e.g., "Monsoon Soiree, last 2 weeks of July to mid August — indulgent rain-side rituals"'
              value={themeText}
              onChange={(e) => setThemeText(e.target.value)}
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Start date (optional)</label>
              <input type="date" value={dateStart} onChange={(e) => setDateStart(e.target.value)} />
            </div>
            <div className="form-group">
              <label>End date (optional)</label>
              <input type="date" value={dateEnd} onChange={(e) => setDateEnd(e.target.value)} />
            </div>
          </div>

          <div className="form-group">
            <label>Property / Brand / City *</label>
            <IntelligentPropertyPicker
              value={pickerSel}
              onChange={setPickerSel}
              scopeSummary={scopeSummary}
            />
            <p style={{ fontSize: 12, color: 'var(--em-ink-soft)', marginTop: 4 }}>
              Chain, mix of hotels, or Club ITC (loyalty) — all supported.
            </p>
          </div>

          <div className="wizard-nav">
            <div className="wizard-nav-spacer" />
            <button className="btn btn-primary" onClick={onStart} disabled={!setupValid || loading}>
              {loading ? <Loader2 size={16} className="spin" /> : <Sparkles size={16} />}
              Start critique
            </button>
          </div>
        </section>
      )}

      {step === 2 && (
        <section className="wizard-panel">
          <h2>Critique</h2>
          <p style={{ color: 'var(--em-ink-soft)', marginTop: -4 }}>
            Sharpening the brief — {describeSelection(pickerSel)}.
          </p>

          {history.length > 0 && (
            <div className="critique-history">
              {history.map((t, i) => (
                <div key={i} className="critique-turn">
                  <div className="critique-q"><MessageCircle size={14} /> {t.q}</div>
                  <div className="critique-a">{t.a}</div>
                </div>
              ))}
            </div>
          )}

          {!readyForShortlist && pendingQuestion && (
            <div className="critique-current">
              <div className="critique-q"><MessageCircle size={14} /> {pendingQuestion}</div>
              <textarea
                rows={3}
                placeholder="Your answer…"
                value={answerText}
                onChange={(e) => setAnswerText(e.target.value)}
              />
            </div>
          )}

          {readyForShortlist && (
            <div className="em-card" style={{ padding: 16, marginTop: 8 }}>
              <strong>Brief looks tight.</strong>
              <p style={{ marginTop: 4, color: 'var(--em-ink-soft)' }}>
                Captured: {Object.entries(captured || {})
                  .filter(([, v]) => v && typeof v === 'string')
                  .map(([k]) => k.replace(/_/g, ' '))
                  .join(', ') || '—'}
              </p>
            </div>
          )}

          <div className="wizard-nav">
            <button className="btn btn-outline" onClick={() => setStep(1)}>
              <ChevronLeft size={16} /> Back
            </button>
            <div className="wizard-nav-spacer" />
            {!readyForShortlist ? (
              <button className="btn btn-primary" onClick={onAnswer} disabled={!answerText.trim() || loading}>
                {loading ? <Loader2 size={16} className="spin" /> : <ChevronRight size={16} />}
                Next
              </button>
            ) : (
              <button className="btn btn-primary" onClick={onGenerateShortlist} disabled={loading}>
                {loading ? <Loader2 size={16} className="spin" /> : <Sparkles size={16} />}
                Generate 10 concepts
              </button>
            )}
          </div>
        </section>
      )}

      {step === 3 && (
        <section className="wizard-panel">
          <h2>Shortlist</h2>
          <p style={{ color: 'var(--em-ink-soft)', marginTop: -4 }}>
            Pick one — it becomes a draft Unified Campaign you can continue editing.
          </p>

          <div className="shortlist-grid">
            {shortlist.map((item, idx) => (
              <article key={idx} className="em-card shortlist-card">
                <header className="shortlist-card-head">
                  <span className="shortlist-card-num">#{idx + 1}</span>
                  <h3>{item.name}</h3>
                </header>
                <p className="shortlist-tagline">{item.tagline}</p>
                <div className="shortlist-section">
                  <span className="em-mono-label">Story line</span>
                  <p>{item.story_line}</p>
                </div>
                <div className="shortlist-section">
                  <span className="em-mono-label">Visual direction</span>
                  <p>{item.visual_direction}</p>
                </div>
                <div className="shortlist-card-foot">
                  <button
                    className="btn btn-primary"
                    onClick={() => onChoose(idx)}
                    disabled={loading}
                  >
                    {loading && chosenIndex === idx ? <Loader2 size={14} className="spin" /> : <ChevronRight size={14} />}
                    Use this concept
                  </button>
                </div>
              </article>
            ))}
          </div>

          <div className="wizard-nav">
            <button className="btn btn-outline" onClick={() => setStep(2)}>
              <ChevronLeft size={16} /> Back to critique
            </button>
            <div className="wizard-nav-spacer" />
            <button className="btn btn-outline" onClick={onGenerateShortlist} disabled={loading}>
              {loading ? <Loader2 size={16} className="spin" /> : <Sparkles size={16} />}
              Regenerate 10
            </button>
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
