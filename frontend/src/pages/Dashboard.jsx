import { useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { generateAds, refineAds, getUrlSuggestions, placesAutocomplete } from '../services/api';
import toast from 'react-hot-toast';
import AdResults from '../components/AdResults';
import GenerationProgress from '../components/GenerationProgress';
import AppNavbar from '../components/AppNavbar';
import { Zap, X, Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

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
  const { user } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    hotel_name: '',
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

  // Refinement
  const [refining, setRefining] = useState(false);

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

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (form.reference_urls.length === 0) {
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
      const payload = {
        ...form,
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
        hotel_name: form.hotel_name,
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

  return (
    <div className="dashboard">
      <AppNavbar />

      <main className="main-content">
        <div className="content-grid">
          <section className="form-panel">
            <h2>Generate Ad Copy</h2>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label>Hotel Name *</label>
                <input name="hotel_name" value={form.hotel_name} onChange={handleChange} required placeholder="e.g., The Grand Hyatt" />
              </div>
              <div className="form-group">
                <label>Offer Name *</label>
                <input name="offer_name" value={form.offer_name} onChange={handleChange} required placeholder="e.g., Summer Escape Package" />
              </div>
              <div className="form-group">
                <label>Inclusions *</label>
                <input name="inclusions" value={form.inclusions} onChange={handleChange} required placeholder="e.g., 20% off + breakfast + spa access" />
              </div>

              {/* Reference URLs with autocomplete */}
              <div className="form-group" style={{ position: 'relative' }}>
                <label>Reference URLs * <span style={{ fontSize: '0.7rem', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>(type URL &amp; press Enter)</span></label>
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
                <label>Campaign Objective</label>
                <select name="campaign_objective" value={form.campaign_objective} onChange={handleChange}>
                  {OBJECTIVES.map((o) => (
                    <option key={o} value={o}>{o || 'Auto-detect'}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Platforms</label>
                <div className="checkbox-grid">
                  {PLATFORMS.map((p) => (
                    <label key={p.id} className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={form.platforms.includes(p.id)}
                        onChange={() => togglePlatform(p.id)}
                      />
                      {p.label}
                    </label>
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

              <button type="submit" className="btn btn-primary btn-full" disabled={loading}>
                {loading ? 'Generating...' : 'Generate Ad Copy'}
              </button>
            </form>
          </section>

          <section className="results-panel">
            {loading ? (
              <GenerationProgress />
            ) : result ? (
              <AdResults data={result} form={form} onRefine={handleRefine} refining={refining} />
            ) : (
              <div className="empty-state">
                <Zap size={48} />
                <h3>Ready to Generate</h3>
                <p>Fill in hotel details and click Generate to create optimized ad copy.</p>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
