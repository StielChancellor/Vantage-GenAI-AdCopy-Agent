import { useState, useRef, useEffect } from 'react';
import { Send, FileText, Save, X, Sparkles, Bot, User } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  copilotChat,
  generateAds,
  refineAds,
  generateCRM,
  refineCRM,
  exportCRMCalendar,
  saveBrief,
  loadBriefs,
  deleteBrief,
} from '../services/api';
import BriefTracker from './BriefTracker';
import BriefSummaryCard from './BriefSummaryCard';
import AdResults from './AdResults';
import CRMResults from './CRMResults';
import CalendarView from './CalendarView';

// ── Brief → Request Mapping ─────────────────────────
function briefToAdRequest(brief) {
  const split = (v) => (v || '').split(',').map((s) => s.trim()).filter(Boolean);
  return {
    hotel_name: brief.identity?.value || '',
    offer_name: brief.offer_name?.value || '',
    inclusions: brief.inclusions?.value || '',
    reference_urls: split(brief.reference_urls?.value),
    google_listing_urls: split(brief.google_listings?.value),
    campaign_objective: brief.campaign_objective?.value || '',
    platforms: split(brief.platforms?.value).length > 0 ? split(brief.platforms?.value) : ['google_search'],
    other_info: '',
  };
}

function briefToCRMRequest(brief) {
  const split = (v) => (v || '').split(',').map((s) => s.trim()).filter(Boolean);
  const schedule = brief.schedule?.value || '';
  const parts = schedule.toLowerCase().includes(' to ') ? schedule.split(/\s+to\s+/i) : ['', ''];
  return {
    hotel_name: brief.identity?.value || '',
    channels: split(brief.channels?.value).length > 0 ? split(brief.channels?.value) : ['email'],
    campaign_type: brief.campaign_type?.value || 'promotional',
    target_audience: brief.target_audience?.value || '',
    offer_details: brief.offer_details?.value || '',
    tone: brief.tone?.value || 'luxurious',
    schedule_start: parts[0]?.trim() || '',
    schedule_end: parts[1]?.trim() || '',
    events: brief.events?.value ? [{ title: brief.events.value, date: '', description: brief.events.value, source: 'copilot', market: 'India' }] : [],
    frequency: 'weekly',
    channel_frequencies: {},
    reference_urls: [],
    google_listing_urls: [],
  };
}

// ── Main Component ──────────────────────────────────
export default function CopilotChat({ mode }) {
  const modeLabel = mode === 'ad_copy' ? 'Ad Copy' : 'CRM Campaign';

  // Chat state
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [brief, setBrief] = useState({});
  const [readyToGenerate, setReadyToGenerate] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);

  // Generation state
  const [generating, setGenerating] = useState(false);
  const [generationResult, setGenerationResult] = useState(null);
  const [refining, setRefining] = useState(false);

  // Brief persistence state
  const [savedBriefs, setSavedBriefs] = useState([]);
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [showLoadPanel, setShowLoadPanel] = useState(false);
  const [briefName, setBriefName] = useState('');

  // Refs
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, readyToGenerate, generationResult]);

  // Load saved briefs on mount
  useEffect(() => {
    loadBriefs(mode)
      .then((res) => setSavedBriefs(res.data.briefs || []))
      .catch(() => {});
  }, [mode]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    }
  }, [input]);

  // ── Handlers ──────────────────────────────────────
  const handleSend = async (e) => {
    e?.preventDefault();
    const text = input.trim();
    if (!text || loading || refining) return;

    // If results already exist, treat input as refinement feedback
    if (generationResult) {
      const userMsg = { role: 'user', content: text, timestamp: new Date().toISOString() };
      setMessages((prev) => [...prev, userMsg]);
      setInput('');
      await handleRefine(text);
      return;
    }

    const userMsg = { role: 'user', content: text, timestamp: new Date().toISOString() };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setInput('');
    setSuggestions([]);
    setLoading(true);

    try {
      const res = await copilotChat({
        mode,
        messages: updatedMessages.map((m) => ({ role: m.role, content: m.content })),
        current_brief: brief,
      });
      const data = res.data;

      const assistantMsg = {
        role: 'assistant',
        content: data.message,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setBrief(data.brief || {});
      setReadyToGenerate(data.ready_to_generate || false);
      setSuggestions(data.suggestions || []);
    } catch (err) {
      const detail = err.response?.data?.detail || 'Chat failed. Please try again.';
      toast.error(detail);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Sorry, something went wrong. Please try again.', timestamp: new Date().toISOString() },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleApproveAndGenerate = async () => {
    setGenerating(true);
    try {
      let result;
      if (mode === 'ad_copy') {
        const payload = briefToAdRequest(brief);
        const res = await generateAds(payload);
        result = res.data;
      } else {
        const payload = briefToCRMRequest(brief);
        const res = await generateCRM(payload);
        result = res.data;
      }
      setGenerationResult(result);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Generation complete! Here are your ${modeLabel} results. You can refine them using the feedback box below.`,
          timestamp: new Date().toISOString(),
          type: 'system',
        },
      ]);
      toast.success(`${modeLabel} generated successfully!`);
    } catch (err) {
      const detail = err.response?.data?.detail || 'Generation failed.';
      toast.error(detail);
    } finally {
      setGenerating(false);
    }
  };

  const handleRefine = async (feedback) => {
    if (!generationResult || !feedback?.trim()) return;
    setRefining(true);
    try {
      let result;
      if (mode === 'ad_copy') {
        const payload = {
          hotel_name: brief.identity?.value || '',
          offer_name: brief.offer_name?.value || '',
          inclusions: brief.inclusions?.value || '',
          platforms: (brief.platforms?.value || 'google_search').split(',').map((s) => s.trim()).filter(Boolean),
          campaign_objective: brief.campaign_objective?.value || '',
          previous_variants: generationResult.variants,
          feedback,
          accumulated_tokens: generationResult.tokens_used || 0,
          accumulated_time: generationResult.time_seconds || 0,
        };
        const res = await refineAds(payload);
        result = { ...generationResult, ...res.data };
      } else {
        const payload = {
          hotel_name: brief.identity?.value || '',
          channels: (brief.channels?.value || 'email').split(',').map((s) => s.trim()).filter(Boolean),
          previous_content: generationResult.content,
          previous_calendar: generationResult.calendar || [],
          feedback,
        };
        const res = await refineCRM(payload);
        result = res.data;
      }
      setGenerationResult(result);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Results refined! The updated output is shown above.',
          timestamp: new Date().toISOString(),
        },
      ]);
      toast.success('Refined successfully!');
    } catch (err) {
      toast.error('Refinement failed.');
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Refinement failed. Please try again.', timestamp: new Date().toISOString() },
      ]);
    } finally {
      setRefining(false);
    }
  };

  const handleFieldClick = (prompt) => {
    setInput(prompt);
    textareaRef.current?.focus();
  };

  const handleEdit = () => {
    setReadyToGenerate(false);
    setInput("I'd like to change some details in the brief.");
    textareaRef.current?.focus();
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleExportCalendar = async () => {
    if (!generationResult?.calendar) return;
    try {
      const res = await exportCRMCalendar(generationResult.calendar);
      const url = window.URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'crm_calendar.csv';
      a.click();
      window.URL.revokeObjectURL(url);
    } catch {
      toast.error('Export failed.');
    }
  };

  // ── Brief Persistence ─────────────────────────────
  const handleSaveBrief = async () => {
    if (!briefName.trim()) {
      toast.error('Please enter a brief name.');
      return;
    }
    try {
      await saveBrief({ mode, name: briefName, brief });
      toast.success('Brief saved!');
      setShowSaveDialog(false);
      setBriefName('');
      const res = await loadBriefs(mode);
      setSavedBriefs(res.data.briefs || []);
    } catch {
      toast.error('Save failed.');
    }
  };

  const handleLoadBrief = (saved) => {
    setBrief(saved.brief);
    const fields = mode === 'ad_copy'
      ? ['identity', 'offer_name', 'inclusions', 'reference_urls', 'platforms']
      : ['identity', 'channels', 'campaign_type', 'target_audience', 'offer_details'];
    const allFilled = fields.every(
      (k) => saved.brief[k]?.confidence !== 'missing' && saved.brief[k]?.value
    );
    setReadyToGenerate(allFilled);
    setMessages((prev) => [
      ...prev,
      {
        role: 'assistant',
        content: `Loaded brief "${saved.name}". ${allFilled ? 'All required fields are filled — ready to generate!' : 'Some fields may need updating. What would you like to change?'}`,
        timestamp: new Date().toISOString(),
        type: 'system',
      },
    ]);
    setShowLoadPanel(false);
    setGenerationResult(null);
    toast.success(`Loaded "${saved.name}"`);
  };

  const handleDeleteBrief = async (briefId) => {
    try {
      await deleteBrief(briefId);
      setSavedBriefs((prev) => prev.filter((b) => b.brief_id !== briefId));
      toast.success('Brief deleted.');
    } catch {
      toast.error('Delete failed.');
    }
  };

  // ── Brief has any data? ───────────────────────────
  const briefHasData = Object.values(brief).some((f) => f?.confidence !== 'missing' && f?.value);

  // ── Render ────────────────────────────────────────
  return (
    <div className="copilot-container">
      {/* Chat Area */}
      <div className="copilot-chat-area">
        {/* Toolbar */}
        <div className="copilot-toolbar">
          <button
            className="btn btn-sm btn-outline"
            onClick={() => setShowLoadPanel(!showLoadPanel)}
          >
            <FileText size={14} /> Saved Briefs{savedBriefs.length > 0 ? ` (${savedBriefs.length})` : ''}
          </button>
          {briefHasData && (
            <button className="btn btn-sm btn-outline" onClick={() => setShowSaveDialog(true)}>
              <Save size={14} /> Save Brief
            </button>
          )}
        </div>

        {/* Saved Briefs Panel */}
        {showLoadPanel && (
          <div className="copilot-briefs-panel">
            {savedBriefs.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', margin: 0 }}>No saved briefs yet.</p>
            ) : (
              savedBriefs.map((b) => (
                <div key={b.brief_id} className="copilot-brief-item">
                  <div>
                    <strong>{b.name}</strong>
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginLeft: '0.5rem' }}>
                      {new Date(b.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '0.3rem', alignItems: 'center' }}>
                    <button className="btn btn-sm btn-primary" onClick={() => handleLoadBrief(b)}>Load</button>
                    <button className="btn-icon" onClick={() => handleDeleteBrief(b.brief_id)} title="Delete">
                      <X size={14} />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* Messages */}
        <div className="copilot-messages">
          {/* Welcome message */}
          {messages.length === 0 && (
            <div className="copilot-welcome">
              <Sparkles size={32} />
              <h3>{modeLabel} Copilot</h3>
              <p>
                Tell me about the campaign you'd like to create. I'll help build your brief
                and generate {mode === 'ad_copy' ? 'ad copy' : 'CRM content'} when you're ready.
              </p>
              <div className="copilot-welcome-examples">
                <button
                  className="copilot-suggestion-chip"
                  onClick={() => setInput(
                    mode === 'ad_copy'
                      ? 'I need Google and Facebook ads for a luxury monsoon spa offer'
                      : 'I want to create a WhatsApp and email campaign for our loyalty members'
                  )}
                >
                  {mode === 'ad_copy' ? 'Create ads for a spa offer' : 'Loyalty campaign for WhatsApp & Email'}
                </button>
                <button
                  className="copilot-suggestion-chip"
                  onClick={() => setInput(
                    mode === 'ad_copy'
                      ? 'Help me create Performance Max and YouTube ads for a summer escape'
                      : 'Re-engagement push notification campaign for dormant guests'
                  )}
                >
                  {mode === 'ad_copy' ? 'PMax + YouTube summer campaign' : 'Re-engagement push notifications'}
                </button>
              </div>
            </div>
          )}

          {/* Message bubbles */}
          {messages.map((msg, i) => (
            <div key={i} className={`copilot-msg copilot-msg-${msg.role}`}>
              <div className="copilot-msg-avatar">
                {msg.role === 'user' ? <User size={14} /> : <Bot size={14} />}
              </div>
              <div className="copilot-msg-content">{msg.content}</div>
            </div>
          ))}

          {/* Typing indicator */}
          {loading && (
            <div className="copilot-msg copilot-msg-assistant">
              <div className="copilot-msg-avatar"><Bot size={14} /></div>
              <div className="copilot-typing">
                <span></span><span></span><span></span>
              </div>
            </div>
          )}

          {/* Brief Summary Card */}
          {readyToGenerate && !generationResult && (
            <BriefSummaryCard
              brief={brief}
              mode={mode}
              onApprove={handleApproveAndGenerate}
              onEdit={handleEdit}
              loading={generating}
            />
          )}

          {/* Inline Results — Ad Copy */}
          {generationResult && mode === 'ad_copy' && (
            <div className="copilot-inline-results">
              <AdResults
                data={generationResult}
                form={{ platforms: (brief.platforms?.value || 'google_search').split(',').map((s) => s.trim()) }}
              />
            </div>
          )}

          {/* Inline Results — CRM */}
          {generationResult && mode === 'crm' && (
            <div className="copilot-inline-results">
              <CRMResults
                content={generationResult.content}
              />
              {generationResult.calendar?.length > 0 && (
                <CalendarView
                  calendar={generationResult.calendar}
                  onExportCSV={handleExportCalendar}
                />
              )}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Quick Suggestions */}
        {suggestions.length > 0 && !generationResult && (
          <div className="copilot-suggestions">
            {suggestions.map((s, i) => (
              <button
                key={i}
                className="copilot-suggestion-chip"
                onClick={() => {
                  setInput(s);
                  textareaRef.current?.focus();
                }}
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Input Area */}
        <form className="copilot-input-area" onSubmit={handleSend}>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={generationResult ? 'Type feedback to refine...' : 'Describe your campaign...'}
            rows={1}
            disabled={loading || generating}
          />
          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading || generating || !input.trim()}
          >
            <Send size={16} />
          </button>
        </form>
      </div>

      {/* Sidebar — Brief Tracker */}
      <div className="copilot-sidebar">
        <BriefTracker brief={brief} mode={mode} onFieldClick={handleFieldClick} />
      </div>

      {/* Save Dialog Modal */}
      {showSaveDialog && (
        <div className="copilot-modal-overlay" onClick={() => setShowSaveDialog(false)}>
          <div className="copilot-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Save Brief</h3>
            <div className="form-group">
              <input
                value={briefName}
                onChange={(e) => setBriefName(e.target.value)}
                placeholder="Brief name..."
                onKeyDown={(e) => e.key === 'Enter' && handleSaveBrief()}
                autoFocus
              />
            </div>
            <div className="copilot-modal-actions">
              <button className="btn btn-outline btn-sm" onClick={() => setShowSaveDialog(false)}>Cancel</button>
              <button className="btn btn-primary btn-sm" onClick={handleSaveBrief}>Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
