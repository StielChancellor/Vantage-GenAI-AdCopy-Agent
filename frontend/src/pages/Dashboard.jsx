import { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import {
  generateAds, refineAds, getUrlSuggestions, placesAutocomplete,
  getMe, getHotelContext, getBrandContext,
} from '../services/api';
import { useSelection } from '../contexts/SelectionContext';
import toast from 'react-hot-toast';
import AdResults from '../components/AdResults';
import GenerationProgress from '../components/GenerationProgress';
import IntelligentPropertyPicker from '../components/IntelligentPropertyPicker';
import RecentGenerations from '../components/RecentGenerations';
import { Zap, X, Plus, Sparkles } from 'lucide-react';
import CopilotChat from '../components/CopilotChat';

const PLATFORMS = [
  { id: 'google_search', label: 'Google Search' },
  { id: 'fb_single_image', label: 'FB Single Image' },
  { id: 'fb_carousel', label: 'FB Carousel' },
  { id: 'fb_video', label: 'FB Video' },
  { id: 'pmax', label: 'Performance Max' },
  { id: 'youtube', label: 'YouTube' },
];

const OBJECTIVES = ['', 'Awareness', 'Consideration', 'Conversion'];

export default function Dashboard() {
  const location = useLocation();
  const { selection, setSelection } = useSelection();
  const [viewMode, setViewMode] = useState('builder');

  // v2.5 — if router state carries a selection (e.g., from the Hub modal),
  // push it into the shared SelectionContext on mount so every other page
  // sees it too.
  useEffect(() => {
    if (location.state?.selection && !selection) setSelection(location.state.selection);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [scopeSummary, setScopeSummary] = useState(null);
  const [autoFilledKeys, setAutoFilledKeys] = useState(new Set());

  const [form, setForm] = useState({
    offer_name: '',
    inclusions: '',
    reference_urls: [],
    google_listing_urls: [],
    other_info: '',
    campaign_objective: '',
    platforms: ['google_search'],
  });
  const [urlInput, setUrlInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  // URL autocomplete
  const [urlSuggestions, setUrlSuggestions] = useState([]);

  // Google Places autocomplete
  const [placeQuery, setPlaceQuery] = useState('');
  const [placeSuggestions, setPlaceSuggestions] = useState([]);

  // Carousel config
  const [carouselMode, setCarouselMode] = useState('suggest');
  const [carouselCards, setCarouselCards] = useState(['', '', '']);

  // v2.4 — generation mode for multi-select picks.
  // 'unified'  → one combined ad copy spanning every entity selected
  // 'per_entity' → one ad per brand + one ad per hotel (server fans out)
  const [fanoutMode, setFanoutMode] = useState('unified');

  // Refinement
  const [refining, setRefining] = useState(false);

  // v2.4 — fetch fresh scope_summary so the picker can render the right UX.
  useEffect(() => {
    (async () => {
      try {
        const r = await getMe();
        setScopeSummary(r.data?.scope_summary || null);
      } catch {
        setScopeSummary(null);
      }
    })();
  }, []);

  // v2.4 — auto-fill the form when the user picks one or more hotels.
  // For 1+ hotels: fetch contexts in parallel and merge ALL website URLs + GMB listings.
  // For 1 brand alone (loyalty or otherwise): fill voice / leave URLs blank — the
  // submit validator below permits empty URL/GMB for brand/loyalty/city scopes.
  useEffect(() => {
    if (!selection) return;
    const hotelIds = selection.hotel_ids || [];
    const brandIds = selection.brand_ids || [];
    const cities = selection.cities || [];
    const onlyBrandsNoHotels =
      brandIds.length === 1 && hotelIds.length === 0 && cities.length === 0;

    let cancelled = false;
    (async () => {
      const filled = new Set();
      try {
        if (hotelIds.length > 0) {
          // Fetch every selected hotel's context in parallel.
          const responses = await Promise.allSettled(
            hotelIds.map((id) => getHotelContext(id))
          );
          if (cancelled) return;
          const newRefUrls = [];
          const newListings = [];
          const summaryBits = [];
          for (const res of responses) {
            if (res.status !== 'fulfilled') continue;
            const h = res.value.data?.hotel || {};
            const gmb = res.value.data?.gmb || {};
            if (h.website_url) newRefUrls.push(h.website_url);
            // Prefer the live GMB record (with real rating + review_count) when present.
            if (gmb.google_url || h.gmb_url) {
              newListings.push({
                name: gmb.name || h.hotel_name || 'Listing',
                place_id: gmb.place_id || h.gmb_place_id || '',
                google_url: gmb.google_url || h.gmb_url,
                rating: gmb.rating || '',
                review_count: gmb.review_count || 0,
                address: gmb.address || h.city || '',
              });
            }
            const bits = [];
            if (h.rooms_count) bits.push(`${h.rooms_count}-room`);
            if (h.fnb_count) bits.push(`${h.fnb_count} F&B`);
            if (h.city) bits.push(h.city);
            if (bits.length) summaryBits.push(`${h.hotel_name}: ${bits.join(' · ')}`);
          }
          setForm((prev) => {
            const refMerged = Array.from(new Set([...(prev.reference_urls || []), ...newRefUrls]));
            // De-dupe listings by google_url.
            const existingUrls = new Set((prev.google_listing_urls || []).map((p) => p.google_url));
            const listingsMerged = [
              ...(prev.google_listing_urls || []),
              ...newListings.filter((l) => l.google_url && !existingUrls.has(l.google_url)),
            ];
            const updates = {};
            if (refMerged.length !== (prev.reference_urls || []).length) {
              updates.reference_urls = refMerged;
              filled.add('reference_urls');
            }
            if (listingsMerged.length !== (prev.google_listing_urls || []).length) {
              updates.google_listing_urls = listingsMerged;
              filled.add('google_listing_urls');
            }
            if (!prev.other_info && summaryBits.length) {
              updates.other_info = summaryBits.join(' · ');
              filled.add('other_info');
            }
            return Object.keys(updates).length ? { ...prev, ...updates } : prev;
          });
        } else if (onlyBrandsNoHotels) {
          // Brand-only / loyalty pick — no per-hotel URLs, just inherit voice.
          const r = await getBrandContext(brandIds[0]);
          if (cancelled) return;
          const b = r.data?.brand || {};
          const isLoyalty = b.kind === 'loyalty';
          setForm((prev) => {
            const updates = {};
            if (!prev.other_info && b.voice) {
              updates.other_info = b.voice;
              filled.add('other_info');
            } else if (isLoyalty && !prev.other_info) {
              updates.other_info = `Loyalty programme: ${b.brand_name}`;
              filled.add('other_info');
            }
            return Object.keys(updates).length ? { ...prev, ...updates } : prev;
          });
        }
      } catch {
        /* best-effort auto-fill; keep existing values on error */
      }
      if (!cancelled && filled.size) setAutoFilledKeys(filled);
    })();

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    (selection?.hotel_ids || []).join(','),
    (selection?.brand_ids || []).join(','),
    (selection?.cities || []).join(','),
  ]);

  // v2.3 keyboard shortcuts: ⌘⏎ generate, ⌘K toggle copilot
  useEffect(() => {
    const onKey = (e) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;
      if (e.key === 'Enter') {
        e.preventDefault();
        const formEl = document.querySelector('form.campaign-form');
        if (formEl) formEl.requestSubmit();
      } else if (e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setViewMode((v) => (v === 'copilot' ? 'builder' : 'copilot'));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // URL suggestions debounce
  useEffect(() => {
    if (urlInput.length < 3) {
      setUrlSuggestions([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const res = await getUrlSuggestions(urlInput);
        setUrlSuggestions(res.data.suggestions || []);
      } catch {
        setUrlSuggestions([]);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [urlInput]);

  // Places autocomplete debounce
  useEffect(() => {
    if (placeQuery.length < 3) {
      setPlaceSuggestions([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const res = await placesAutocomplete(placeQuery);
        setPlaceSuggestions(res.data.suggestions || []);
      } catch {
        setPlaceSuggestions([]);
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [placeQuery]);

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const togglePlatform = (pid) => {
    setForm((prev) => ({
      ...prev,
      platforms: prev.platforms.includes(pid)
        ? prev.platforms.filter((p) => p !== pid)
        : [...prev.platforms, pid],
    }));
  };

  // Multi-URL tag handlers
  const addUrl = (url) => {
    let trimmed = url.trim();
    if (!trimmed) return;
    // Auto-prepend https:// if no protocol
    if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) {
      trimmed = 'https://' + trimmed;
    }
    // Basic URL validation
    try {
      new URL(trimmed);
    } catch {
      toast.error('Please enter a valid URL');
      return;
    }
    if (form.reference_urls.includes(trimmed)) {
      toast.error('URL already added');
      return;
    }
    setForm((prev) => ({
      ...prev,
      reference_urls: [...prev.reference_urls, trimmed],
    }));
    setUrlInput('');
    setUrlSuggestions([]);
  };

  const removeUrl = (index) => {
    setForm((prev) => ({
      ...prev,
      reference_urls: prev.reference_urls.filter((_, i) => i !== index),
    }));
  };

  const handleUrlKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addUrl(urlInput);
    }
    // Backspace on empty input removes last tag
    if (e.key === 'Backspace' && urlInput === '' && form.reference_urls.length > 0) {
      removeUrl(form.reference_urls.length - 1);
    }
  };

  // Google Places handlers
  const selectPlace = (place) => {
    // Avoid duplicates by place_id
    if (form.google_listing_urls.find(p => p.place_id === place.place_id)) {
      toast.error('Listing already added');
      return;
    }
    setForm((prev) => ({
      ...prev,
      google_listing_urls: [...prev.google_listing_urls, place],
    }));
    setPlaceQuery('');
    setPlaceSuggestions([]);
  };

  const removeListing = (index) => {
    setForm((prev) => ({
      ...prev,
      google_listing_urls: prev.google_listing_urls.filter((_, i) => i !== index),
    }));
  };

  // v2.4 — derive hotel_name + selection payload from the IntelligentPropertyPicker state.
  const buildHotelName = () => {
    if (!selection) return '';
    if ((selection._labels?.hotels?.length || 0) === 1) return selection._labels.hotels[0].label;
    if ((selection._labels?.brands?.length || 0) === 1) return selection._labels.brands[0].label;
    if ((selection._labels?.cities?.length || 0) === 1) return selection._labels.cities[0].label;
    // Multi: comma-join labels for the audit log.
    const all = [
      ...(selection._labels?.brands || []).map((b) => b.label),
      ...(selection._labels?.hotels || []).map((h) => h.label),
      ...(selection._labels?.cities || []).map((c) => c.label),
    ];
    return all.join(', ');
  };

  const isSelectionValid = () => {
    if (!selection) return false;
    return (
      (selection.hotel_ids?.length || 0) +
      (selection.brand_ids?.length || 0) +
      (selection.cities?.length || 0)
    ) > 0;
  };

  const buildSelectionPayload = () => {
    if (!selection) return undefined;
    return {
      scope: selection.scope || 'hotel',
      hotel_id: selection.hotel_ids?.[0] || '',
      brand_id: selection.brand_ids?.[0] || '',
      hotel_ids: selection.hotel_ids || [],
      brand_ids: selection.brand_ids || [],
      cities: selection.cities || [],
      is_loyalty: !!selection.is_loyalty,
      generation_mode: needsFanoutPrompt() ? fanoutMode : undefined,
    };
  };

  // v2.4 — when the user has picked more than one entity (multiple hotels,
  // multiple brands, brand+hotels, etc.) we need to ask whether to combine
  // them into a single ad or fan out per entity.
  const needsFanoutPrompt = () => {
    if (!selection) return false;
    const entities =
      (selection.hotel_ids?.length || 0) +
      (selection.brand_ids?.length || 0) +
      (selection.cities?.length || 0);
    return entities > 1;
  };

  // v2.4 — for brand / loyalty / city scopes the URL + GMB fields can stay empty.
  const urlOptional = () => {
    if (!selection) return false;
    const noHotels = (selection.hotel_ids?.length || 0) === 0;
    return noHotels && (
      (selection.brand_ids?.length || 0) > 0 ||
      (selection.cities?.length || 0) > 0 ||
      selection.is_loyalty
    );
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!isSelectionValid()) {
      toast.error('Pick a hotel, brand, or city to start.');
      return;
    }
    if (!urlOptional() && form.reference_urls.length === 0) {
      toast.error('Add at least one reference URL');
      return;
    }
    if (form.platforms.length === 0) {
      toast.error('Select at least one platform');
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const hotelName = buildHotelName();
      const payload = {
        ...form,
        hotel_name: hotelName,
        selection: buildSelectionPayload(),
        google_listing_urls: form.google_listing_urls.map(p => p.google_url || ''),
        carousel_mode: form.platforms.includes('fb_carousel') ? carouselMode : undefined,
        carousel_cards: form.platforms.includes('fb_carousel') && carouselMode === 'manual'
          ? carouselCards.filter(c => c.trim())
          : undefined,
      };
      const res = await generateAds(payload);
      setResult(res.data);
      toast.success(`Generated! ${res.data.tokens_used} tokens used in ${res.data.time_seconds?.toFixed(1)}s`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Generation failed');
    } finally {
      setLoading(false);
    }
  };

  const handleRefine = async (feedback) => {
    setRefining(true);
    try {
      const payload = {
        hotel_name: buildHotelName(),
        offer_name: form.offer_name,
        inclusions: form.inclusions,
        platforms: form.platforms,
        campaign_objective: form.campaign_objective,
        other_info: form.other_info,
        previous_variants: result.variants,
        feedback: feedback,
        accumulated_tokens: result.tokens_used,
        accumulated_time: result.time_seconds,
      };
      const res = await refineAds(payload);
      setResult(res.data);
      toast.success(`Refined! +${(res.data.input_tokens + res.data.output_tokens).toLocaleString()} tokens`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Refinement failed');
    } finally {
      setRefining(false);
    }
  };

  // v2.4 — repopulate the form fields from a recent generation row.
  const handleReuseBrief = (row) => {
    if (!row) return;
    const platforms = (row.platforms && row.platforms.length) ? row.platforms : form.platforms;
    setForm((prev) => ({
      ...prev,
      offer_name: row.offer_name || prev.offer_name,
      inclusions: row.inclusions || prev.inclusions,
      reference_urls: row.reference_urls?.length ? row.reference_urls : prev.reference_urls,
      campaign_objective: row.campaign_objective || prev.campaign_objective,
      platforms,
    }));
    toast.success('Brief restored — review and generate.');
    // Scroll back to the form.
    requestAnimationFrame(() => {
      const el = document.querySelector('form.campaign-form');
      el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };

  return (
    <>
      <div className="page-header">
        <h1>Ad Copy</h1>
        <div className="mode-toggle">
          <button className={`mode-toggle-pill ${viewMode === 'builder' ? 'active' : ''}`} onClick={() => setViewMode('builder')}>
            Builder
          </button>
          <button className={`mode-toggle-pill ${viewMode === 'copilot' ? 'active' : ''}`} onClick={() => setViewMode('copilot')}>
            <Sparkles size={14} /> Copilot
          </button>
        </div>
      </div>

      {viewMode === 'copilot' ? (
        <CopilotChat mode="ad_copy" />
      ) : (
        <>
        <div className="page-centered">
          <form className="campaign-form" onSubmit={handleSubmit}>
            <div className="form-group">
              <label>Property / Brand / City *</label>
              <IntelligentPropertyPicker
                value={selection}
                onChange={setSelection}
                scopeSummary={scopeSummary}
              />
              {selection?.is_loyalty && (
                <p style={{ fontSize: 12, color: 'var(--em-accent, #c8331e)', marginTop: 6 }}>
                  Loyalty mode — ads will draw on chain-wide voice (anonymized exemplars from every partner brand). GMB and per-property fields are ignored.
                </p>
              )}
              {needsFanoutPrompt() && (
                <div className="form-group" style={{ marginTop: 12 }}>
                  <label>Generation mode</label>
                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                    <label className="radio-label" style={{ flex: '1 1 240px' }}>
                      <input
                        type="radio"
                        name="fanout-mode"
                        value="unified"
                        checked={fanoutMode === 'unified'}
                        onChange={() => setFanoutMode('unified')}
                      />
                      One combined ad copy across every selection
                    </label>
                    <label className="radio-label" style={{ flex: '1 1 240px' }}>
                      <input
                        type="radio"
                        name="fanout-mode"
                        value="per_entity"
                        checked={fanoutMode === 'per_entity'}
                        onChange={() => setFanoutMode('per_entity')}
                      />
                      Separate ad copy per brand + per hotel
                    </label>
                  </div>
                </div>
              )}
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Offer Name *</label>
                <input name="offer_name" value={form.offer_name} onChange={handleChange} required placeholder="e.g., Summer Escape Package" />
              </div>
              <div className="form-group">
                <label>Campaign Objective</label>
                <select name="campaign_objective" value={form.campaign_objective} onChange={handleChange}>
                  {OBJECTIVES.map((o) => (
                    <option key={o} value={o}>{o || 'Auto-detect'}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="form-group">
              <label>Inclusions *</label>
              <input name="inclusions" value={form.inclusions} onChange={handleChange} required placeholder="e.g., 20% off + breakfast + spa access" />
            </div>

              {/* Reference URLs with autocomplete */}
              <div className="form-group" style={{ position: 'relative' }}>
                <label>
                  Reference URLs {urlOptional() ? '' : '*'}
                  {' '}
                  <span style={{ fontSize: '0.7rem', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>
                    {urlOptional()
                      ? '(optional for brand / loyalty / city scope)'
                      : '(type URL & press Enter)'}
                  </span>
                </label>
                <div className="url-tags-container" onClick={() => document.getElementById('url-input').focus()}>
                  {form.reference_urls.map((url, i) => (
                    <div key={i} className="url-tag">
                      <span>{url.replace(/^https?:\/\//, '').slice(0, 40)}</span>
                      <button type="button" onClick={() => removeUrl(i)}><X size={12} /></button>
                    </div>
                  ))}
                  <input
                    id="url-input"
                    className="url-tags-input"
                    type="text"
                    value={urlInput}
                    onChange={(e) => setUrlInput(e.target.value)}
                    onKeyDown={handleUrlKeyDown}
                    onBlur={() => { if (urlInput.trim()) addUrl(urlInput); }}
                    placeholder={form.reference_urls.length === 0 ? 'hotel-website.com or paste full URL' : 'Add another URL...'}
                  />
                </div>
                {urlSuggestions.length > 0 && (
                  <div className="autocomplete-dropdown">
                    {urlSuggestions.map((s, i) => (
                      <div key={i} className="autocomplete-item" onMouseDown={() => { addUrl(s); }}>
                        {s.replace(/^https?:\/\//, '').slice(0, 60)}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Google Listing with Places autocomplete */}
              <div className="form-group" style={{ position: 'relative' }}>
                <label>Google Listing(s) <span style={{ fontSize: '0.7rem', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>(search by hotel name)</span></label>
                <div className="url-tags-container" onClick={() => document.getElementById('place-input').focus()}>
                  {form.google_listing_urls.map((place, i) => (
                    <div key={i} className="url-tag">
                      <span>{place.name} ({place.review_count} reviews)</span>
                      <button type="button" onClick={() => removeListing(i)}><X size={12} /></button>
                    </div>
                  ))}
                  <input
                    id="place-input"
                    className="url-tags-input"
                    type="text"
                    value={placeQuery}
                    onChange={(e) => setPlaceQuery(e.target.value)}
                    placeholder={form.google_listing_urls.length === 0 ? 'Search for hotel...' : 'Add another listing...'}
                  />
                </div>
                {placeSuggestions.length > 0 && (
                  <div className="autocomplete-dropdown">
                    {placeSuggestions.map((s, i) => (
                      <div key={i} className="autocomplete-item place-item" onMouseDown={() => selectPlace(s)}>
                        <div className="place-name">{s.name}</div>
                        <div className="place-meta">{s.address} &middot; {s.rating}&#9733; &middot; {s.review_count} reviews</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="form-group">
                <label>Other Information</label>
                <textarea name="other_info" value={form.other_info} onChange={handleChange} rows={2} placeholder="Any additional context..." />
              </div>
            <div className="form-group">
              <label>Platforms</label>
              <div className="platform-pills">
                {PLATFORMS.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    className={`platform-pill ${form.platforms.includes(p.id) ? 'active' : ''}`}
                    onClick={() => togglePlatform(p.id)}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Carousel card config (when fb_carousel selected) */}
            {form.platforms.includes('fb_carousel') && (
              <div className="form-group carousel-config" style={{ animation: 'fadeSlideUp 0.3s ease' }}>
                <label>Carousel Card Setup</label>
                <div className="radio-group">
                  <label className="radio-label">
                    <input type="radio" name="carouselMode" value="suggest" checked={carouselMode === 'suggest'} onChange={() => setCarouselMode('suggest')} />
                    Suggest carousel flow (AI recommends card visuals)
                  </label>
                  <label className="radio-label">
                    <input type="radio" name="carouselMode" value="manual" checked={carouselMode === 'manual'} onChange={() => setCarouselMode('manual')} />
                    Provide details for each card
                  </label>
                </div>
                {carouselMode === 'manual' && (
                  <div className="carousel-cards-input">
                    {carouselCards.map((card, i) => (
                      <div key={i} className="card-input-row">
                        <span className="card-number">Card {i + 1}</span>
                        <input
                          value={card}
                          onChange={(e) => {
                            const updated = [...carouselCards];
                            updated[i] = e.target.value;
                            setCarouselCards(updated);
                          }}
                          placeholder="e.g., Hotel facade with doorman greeting guests"
                        />
                        {carouselCards.length > 2 && (
                          <button type="button" className="btn-icon danger" onClick={() => setCarouselCards(carouselCards.filter((_, j) => j !== i))}>
                            <X size={14} />
                          </button>
                        )}
                      </div>
                    ))}
                    {carouselCards.length < 10 && (
                      <button type="button" className="btn btn-sm btn-outline" onClick={() => setCarouselCards([...carouselCards, ''])}>
                        <Plus size={14} /> Add Card
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}

            <div className="em-builder-foot" style={{ marginTop: 18, paddingTop: 14, borderTop: '1px solid var(--em-line)' }}>
              <div className="em-kbd-hint">
                <span className="k">⌘</span> <span className="k">⏎</span> generate ·
                {' '}<span className="k">⌘</span> <span className="k">K</span> switch to Copilot
              </div>
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? 'Generating...' : <><Zap size={16} /> Generate Ad Copy</>}
              </button>
            </div>
          </form>
        </div>

        {loading && (
          <div className="page-centered" style={{ marginTop: '1.5rem' }}>
            <GenerationProgress />
          </div>
        )}

        {result && !loading && (
          <div className="page-centered" style={{ marginTop: '1.5rem' }}>
            <AdResults data={result} form={form} onRefine={handleRefine} refining={refining} />
          </div>
        )}

        {/* v2.4 — Pick up where you left off */}
        <div className="page-centered">
          <RecentGenerations
            hotelId={selection?.hotel_ids?.[0] || ''}
            brandId={selection?.brand_ids?.[0] || ''}
            limit={10}
            onReuse={handleReuseBrief}
          />
        </div>
        </>
      )}
    </>
  );
}
