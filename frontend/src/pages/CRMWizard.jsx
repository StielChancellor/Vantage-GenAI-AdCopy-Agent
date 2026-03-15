import { useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { generateCRM, refineCRM, searchEvents, exportCRMCalendar, placesAutocomplete } from '../services/api';
import toast from 'react-hot-toast';
import AppNavbar from '../components/AppNavbar';
import CRMResults from '../components/CRMResults';
import CalendarView from '../components/CalendarView';
import GenerationProgress from '../components/GenerationProgress';
import ContextSelector, { getHotelNameFromContext, isContextValid } from '../components/ContextSelector';
import ChannelFrequency from '../components/ChannelFrequency';
import EventCalendar from '../components/EventCalendar';
import { Zap, X, Plus, Search, ChevronRight, ChevronLeft, Calendar, MessageSquare } from 'lucide-react';

const CHANNELS = [
  { id: 'whatsapp', label: 'WhatsApp', color: '#25d366' },
  { id: 'email', label: 'Email', color: '#4a90d9' },
  { id: 'app_push', label: 'App Push', color: '#9b59b6' },
];

const CAMPAIGN_TYPES = [
  { id: 'promotional', label: 'Promotional' },
  { id: 'seasonal', label: 'Seasonal' },
  { id: 'event', label: 'Event-Based' },
  { id: 'loyalty', label: 'Loyalty' },
  { id: 're-engagement', label: 'Re-engagement' },
];

const TONES = [
  { id: 'luxurious', label: 'Luxurious' },
  { id: 'formal', label: 'Formal' },
  { id: 'casual', label: 'Casual' },
  { id: 'urgent', label: 'Urgent' },
];

const EVENT_CATEGORIES = ['festivals', 'holidays', 'sports', 'conferences'];

const STEPS = [
  { num: 1, label: 'Identity & Channels' },
  { num: 2, label: 'Campaign Details' },
  { num: 3, label: 'Events' },
  { num: 4, label: 'Schedule' },
  { num: 5, label: 'Results' },
];

export default function CRMWizard() {
  const { user } = useAuth();
  const [step, setStep] = useState(1);

  // Step 1: Context & Channel
  const [context, setContext] = useState({
    context_type: 'single_property',
    property_names: [],
    destination_name: '',
    generation_mode: 'unified',
  });
  const [channels, setChannels] = useState([]);
  const [campaignType, setCampaignType] = useState('promotional');
  const [referenceUrls, setReferenceUrls] = useState([]);
  const [urlInput, setUrlInput] = useState('');
  const [googleListings, setGoogleListings] = useState([]);
  const [placeQuery, setPlaceQuery] = useState('');
  const [placeSuggestions, setPlaceSuggestions] = useState([]);

  // Step 2: Campaign Details
  const [targetAudience, setTargetAudience] = useState('');
  const [offerDetails, setOfferDetails] = useState('');
  const [inclusions, setInclusions] = useState('');
  const [tone, setTone] = useState('luxurious');
  const [otherInfo, setOtherInfo] = useState('');

  // Step 3: Events
  const [markets, setMarkets] = useState(['India']);
  const [marketInput, setMarketInput] = useState('');
  const [dateRangeStart, setDateRangeStart] = useState('');
  const [dateRangeEnd, setDateRangeEnd] = useState('');
  const [selectedCategories, setSelectedCategories] = useState(['festivals', 'holidays']);
  const [eventResults, setEventResults] = useState([]);
  const [selectedEvents, setSelectedEvents] = useState([]);
  const [searchingEvents, setSearchingEvents] = useState(false);

  // Step 4: Schedule & Frequency
  const [scheduleStart, setScheduleStart] = useState('');
  const [scheduleEnd, setScheduleEnd] = useState('');
  const [channelFrequencies, setChannelFrequencies] = useState({});
  const [frequency, setFrequency] = useState('weekly'); // Fallback

  // Step 5: Results
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [refining, setRefining] = useState(false);
  const [resultTab, setResultTab] = useState('messages');

  // Places autocomplete
  useEffect(() => {
    if (placeQuery.length < 3) { setPlaceSuggestions([]); return; }
    const timer = setTimeout(async () => {
      try {
        const res = await placesAutocomplete(placeQuery);
        setPlaceSuggestions(res.data.suggestions || []);
      } catch { setPlaceSuggestions([]); }
    }, 400);
    return () => clearTimeout(timer);
  }, [placeQuery]);

  const toggleChannel = (id) => {
    setChannels((prev) => prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id]);
  };

  const toggleCategory = (cat) => {
    setSelectedCategories((prev) => prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]);
  };

  const addUrl = (url) => {
    let trimmed = url.trim();
    if (!trimmed) return;
    if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) trimmed = 'https://' + trimmed;
    try { new URL(trimmed); } catch { toast.error('Invalid URL'); return; }
    if (referenceUrls.includes(trimmed)) return;
    setReferenceUrls((prev) => [...prev, trimmed]);
    setUrlInput('');
  };

  const addMarket = () => {
    const m = marketInput.trim();
    if (m && !markets.includes(m)) {
      setMarkets((prev) => [...prev, m]);
      setMarketInput('');
    }
  };

  const handleSearchEvents = async () => {
    setSearchingEvents(true);
    try {
      const res = await searchEvents({
        markets,
        date_range_start: dateRangeStart,
        date_range_end: dateRangeEnd,
        categories: selectedCategories,
      });
      setEventResults(res.data || []);
      if (res.data?.length === 0) toast('No events found. Try adjusting filters.');
    } catch {
      toast.error('Event search failed');
    } finally {
      setSearchingEvents(false);
    }
  };

  const toggleEvent = (event) => {
    setSelectedEvents((prev) => {
      const exists = prev.find((e) => e.title === event.title && e.date === event.date);
      if (exists) return prev.filter((e) => !(e.title === event.title && e.date === event.date));
      return [...prev, event];
    });
  };

  const handleGenerate = async () => {
    setLoading(true);
    setResult(null);
    setStep(5);
    try {
      const hotelName = getHotelNameFromContext(context);
      const payload = {
        hotel_name: hotelName,
        context,
        channels,
        campaign_type: campaignType,
        target_audience: targetAudience,
        offer_details: offerDetails,
        tone,
        events: selectedEvents.map((e) => ({ title: e.title, date: e.date, description: e.description, source: e.source, market: e.market })),
        schedule_start: scheduleStart,
        schedule_end: scheduleEnd,
        frequency,
        channel_frequencies: channelFrequencies,
        inclusions,
        other_info: otherInfo,
        reference_urls: referenceUrls,
        google_listing_urls: googleListings.map((p) => p.google_url || ''),
      };
      const res = await generateCRM(payload);
      setResult(res.data);
      toast.success(`Generated! ${res.data.tokens_used} tokens in ${res.data.time_seconds?.toFixed(1)}s`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'CRM generation failed');
      setStep(4);
    } finally {
      setLoading(false);
    }
  };

  const handleRefine = async (feedback) => {
    setRefining(true);
    try {
      const res = await refineCRM({
        hotel_name: getHotelNameFromContext(context),
        channels,
        previous_content: result.content,
        previous_calendar: result.calendar,
        feedback,
      });
      setResult(res.data);
      toast.success('Content refined');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Refinement failed');
    } finally {
      setRefining(false);
    }
  };

  const handleExportCSV = async () => {
    try {
      const res = await exportCRMCalendar(result.calendar);
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'crm_calendar.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success('Calendar exported');
    } catch {
      toast.error('Export failed');
    }
  };

  const canProceed = () => {
    switch (step) {
      case 1: return isContextValid(context) && channels.length > 0;
      case 2: return targetAudience.trim() && offerDetails.trim();
      case 3: return true; // Events are optional
      case 4: return scheduleStart && scheduleEnd;
      default: return true;
    }
  };

  const hotelName = getHotelNameFromContext(context);

  return (
    <div className="dashboard">
      <AppNavbar />

      <main className="main-content">
        {/* Step indicator */}
        <div className="wizard-steps">
          {STEPS.map((s) => (
            <div key={s.num} className={`wizard-step ${step === s.num ? 'active' : ''} ${step > s.num ? 'completed' : ''}`}>
              <div className="wizard-step-circle">{step > s.num ? '✓' : s.num}</div>
              <span className="wizard-step-label">{s.label}</span>
            </div>
          ))}
        </div>

        <div className="wizard-content">
          {/* STEP 1: Identity & Channels */}
          {step === 1 && (
            <section className="wizard-panel">
              <h2>Identity & Channel Selection</h2>

              <ContextSelector value={context} onChange={setContext} />

              <div className="form-group" style={{ marginTop: '1rem' }}>
                <label>Channels *</label>
                <div className="checkbox-grid">
                  {CHANNELS.map((ch) => (
                    <label key={ch.id} className="checkbox-label channel-checkbox" style={{ borderColor: channels.includes(ch.id) ? ch.color : 'transparent' }}>
                      <input type="checkbox" checked={channels.includes(ch.id)} onChange={() => toggleChannel(ch.id)} />
                      {ch.label}
                    </label>
                  ))}
                </div>
              </div>

              <div className="form-group">
                <label>Campaign Type</label>
                <select value={campaignType} onChange={(e) => setCampaignType(e.target.value)}>
                  {CAMPAIGN_TYPES.map((ct) => (
                    <option key={ct.id} value={ct.id}>{ct.label}</option>
                  ))}
                </select>
              </div>

              {/* Reference URLs */}
              <div className="form-group" style={{ position: 'relative' }}>
                <label>Reference URLs <span style={{ fontSize: '0.7rem', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>(optional)</span></label>
                <div className="url-tags-container" onClick={() => document.getElementById('crm-url-input')?.focus()}>
                  {referenceUrls.map((url, i) => (
                    <div key={i} className="url-tag">
                      <span>{url.replace(/^https?:\/\//, '').slice(0, 40)}</span>
                      <button type="button" onClick={() => setReferenceUrls((prev) => prev.filter((_, j) => j !== i))}><X size={12} /></button>
                    </div>
                  ))}
                  <input
                    id="crm-url-input"
                    className="url-tags-input"
                    value={urlInput}
                    onChange={(e) => setUrlInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addUrl(urlInput); } }}
                    onBlur={() => { if (urlInput.trim()) addUrl(urlInput); }}
                    placeholder="hotel-website.com"
                  />
                </div>
              </div>

              {/* Google Listing */}
              <div className="form-group" style={{ position: 'relative' }}>
                <label>Google Listing(s) <span style={{ fontSize: '0.7rem', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>(optional)</span></label>
                <div className="url-tags-container" onClick={() => document.getElementById('crm-place-input')?.focus()}>
                  {googleListings.map((place, i) => (
                    <div key={i} className="url-tag">
                      <span>{place.name}</span>
                      <button type="button" onClick={() => setGoogleListings((prev) => prev.filter((_, j) => j !== i))}><X size={12} /></button>
                    </div>
                  ))}
                  <input
                    id="crm-place-input"
                    className="url-tags-input"
                    value={placeQuery}
                    onChange={(e) => setPlaceQuery(e.target.value)}
                    placeholder="Search for hotel..."
                  />
                </div>
                {placeSuggestions.length > 0 && (
                  <div className="autocomplete-dropdown">
                    {placeSuggestions.map((s, i) => (
                      <div key={i} className="autocomplete-item place-item" onMouseDown={() => {
                        if (!googleListings.find((p) => p.place_id === s.place_id)) {
                          setGoogleListings((prev) => [...prev, s]);
                        }
                        setPlaceQuery(''); setPlaceSuggestions([]);
                      }}>
                        <div className="place-name">{s.name}</div>
                        <div className="place-meta">{s.address} &middot; {s.rating}&#9733;</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          )}

          {/* STEP 2: Campaign Details */}
          {step === 2 && (
            <section className="wizard-panel">
              <h2>Campaign Details</h2>

              <div className="form-group">
                <label>Target Audience *</label>
                <textarea value={targetAudience} onChange={(e) => setTargetAudience(e.target.value)} rows={2} placeholder="e.g., Luxury travelers aged 30-55, couples looking for weekend getaways" />
              </div>

              <div className="form-group">
                <label>Offer Details *</label>
                <textarea value={offerDetails} onChange={(e) => setOfferDetails(e.target.value)} rows={2} placeholder="e.g., 30% off on suites + complimentary spa for 2" />
              </div>

              <div className="form-group">
                <label>Inclusions</label>
                <input value={inclusions} onChange={(e) => setInclusions(e.target.value)} placeholder="e.g., Breakfast, airport transfer, late checkout" />
              </div>

              <div className="form-group">
                <label>Tone</label>
                <div className="checkbox-grid">
                  {TONES.map((t) => (
                    <label key={t.id} className="radio-label">
                      <input type="radio" name="tone" value={t.id} checked={tone === t.id} onChange={() => setTone(t.id)} />
                      {t.label}
                    </label>
                  ))}
                </div>
              </div>

              <div className="form-group">
                <label>Additional Information</label>
                <textarea value={otherInfo} onChange={(e) => setOtherInfo(e.target.value)} rows={2} placeholder="Any extra context..." />
              </div>
            </section>
          )}

          {/* STEP 3: Events */}
          {step === 3 && (
            <section className="wizard-panel">
              <h2>Event Selection <span style={{ fontSize: '0.8rem', fontWeight: 400 }}>(optional)</span></h2>

              <div className="form-group">
                <label>Markets</label>
                <div className="url-tags-container">
                  {markets.map((m, i) => (
                    <div key={i} className="url-tag">
                      <span>{m}</span>
                      {m !== 'India' && (
                        <button type="button" onClick={() => setMarkets((prev) => prev.filter((_, j) => j !== i))}><X size={12} /></button>
                      )}
                    </div>
                  ))}
                  <input
                    className="url-tags-input"
                    value={marketInput}
                    onChange={(e) => setMarketInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addMarket(); } }}
                    placeholder="Add market..."
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Date Range Start</label>
                  <input type="date" value={dateRangeStart} onChange={(e) => setDateRangeStart(e.target.value)} />
                </div>
                <div className="form-group">
                  <label>Date Range End</label>
                  <input type="date" value={dateRangeEnd} onChange={(e) => setDateRangeEnd(e.target.value)} />
                </div>
              </div>

              <div className="form-group">
                <label>Categories</label>
                <div className="checkbox-grid">
                  {EVENT_CATEGORIES.map((cat) => (
                    <label key={cat} className="checkbox-label">
                      <input type="checkbox" checked={selectedCategories.includes(cat)} onChange={() => toggleCategory(cat)} />
                      {cat.charAt(0).toUpperCase() + cat.slice(1)}
                    </label>
                  ))}
                </div>
              </div>

              <button className="btn btn-primary" onClick={handleSearchEvents} disabled={searchingEvents}>
                <Search size={16} /> {searchingEvents ? 'Searching...' : 'Search Events'}
              </button>

              {/* Event results — Calendar/Timeline toggle */}
              {eventResults.length > 0 && (
                <>
                  <h4 style={{ marginTop: '1rem' }}>Found {eventResults.length} Events</h4>
                  <EventCalendar
                    events={eventResults}
                    selectedEvents={selectedEvents}
                    onToggleEvent={toggleEvent}
                  />
                </>
              )}

              {selectedEvents.length > 0 && (
                <div className="selected-events-summary">
                  <strong>{selectedEvents.length} event(s) selected</strong>
                </div>
              )}
            </section>
          )}

          {/* STEP 4: Schedule & Frequency */}
          {step === 4 && (
            <section className="wizard-panel">
              <h2>Campaign Schedule</h2>

              <div className="form-row">
                <div className="form-group">
                  <label>Start Date *</label>
                  <input type="date" value={scheduleStart} onChange={(e) => setScheduleStart(e.target.value)} required />
                </div>
                <div className="form-group">
                  <label>End Date *</label>
                  <input type="date" value={scheduleEnd} onChange={(e) => setScheduleEnd(e.target.value)} required />
                </div>
              </div>

              {/* Per-Channel Frequency */}
              <div className="form-group">
                <label>Per-Channel Frequency</label>
                <ChannelFrequency
                  channels={channels}
                  value={channelFrequencies}
                  onChange={setChannelFrequencies}
                />
              </div>

              {/* Summary */}
              <div className="wizard-summary">
                <h4>Campaign Summary</h4>
                <div className="summary-grid">
                  <div><strong>Identity:</strong> {hotelName || '-'}</div>
                  <div><strong>Channels:</strong> {channels.map((c) => CHANNELS.find((ch) => ch.id === c)?.label).join(', ')}</div>
                  <div><strong>Type:</strong> {CAMPAIGN_TYPES.find((ct) => ct.id === campaignType)?.label}</div>
                  <div><strong>Tone:</strong> {TONES.find((t) => t.id === tone)?.label}</div>
                  <div><strong>Audience:</strong> {targetAudience.slice(0, 60)}{targetAudience.length > 60 ? '...' : ''}</div>
                  {selectedEvents.length > 0 && <div><strong>Events:</strong> {selectedEvents.length} selected</div>}
                </div>
              </div>
            </section>
          )}

          {/* STEP 5: Results */}
          {step === 5 && (
            <section className="wizard-panel wizard-panel-wide">
              {loading ? (
                <GenerationProgress />
              ) : result ? (
                <>
                  <div className="result-tabs">
                    <button className={`result-tab ${resultTab === 'messages' ? 'active' : ''}`} onClick={() => setResultTab('messages')}>
                      <MessageSquare size={16} /> Messages
                    </button>
                    <button className={`result-tab ${resultTab === 'calendar' ? 'active' : ''}`} onClick={() => setResultTab('calendar')}>
                      <Calendar size={16} /> Calendar
                    </button>
                  </div>

                  {resultTab === 'messages' ? (
                    <CRMResults content={result.content} onRefine={handleRefine} refining={refining} />
                  ) : (
                    <CalendarView calendar={result.calendar} onExportCSV={handleExportCSV} />
                  )}

                  <div className="generation-meta">
                    <span>{result.tokens_used?.toLocaleString()} tokens</span>
                    <span>{result.time_seconds?.toFixed(1)}s</span>
                    <span>{result.model_used}</span>
                  </div>
                </>
              ) : (
                <div className="empty-state">
                  <Zap size={48} />
                  <h3>Ready to Generate</h3>
                  <p>Complete the wizard steps and generate your CRM campaign.</p>
                </div>
              )}
            </section>
          )}

          {/* Navigation buttons */}
          {step < 5 && (
            <div className="wizard-nav">
              {step > 1 && (
                <button className="btn btn-outline" onClick={() => setStep(step - 1)}>
                  <ChevronLeft size={16} /> Back
                </button>
              )}
              <div className="wizard-nav-spacer" />
              {step < 4 ? (
                <button className="btn btn-primary" onClick={() => setStep(step + 1)} disabled={!canProceed()}>
                  Next <ChevronRight size={16} />
                </button>
              ) : (
                <button className="btn btn-primary btn-generate" onClick={handleGenerate} disabled={!canProceed()}>
                  <Zap size={16} /> Generate Campaign
                </button>
              )}
            </div>
          )}

          {step === 5 && result && (
            <div className="wizard-nav">
              <button className="btn btn-outline" onClick={() => setStep(4)}>
                <ChevronLeft size={16} /> Back to Schedule
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
